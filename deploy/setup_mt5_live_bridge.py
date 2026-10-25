"""Guided Fedora LIVE read-only deployment. Never opens Ledger's production DB."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time

SERVICE='ledger-mt5-live-bridge.service'
ROOT=Path(__file__).resolve().parents[1]

# Atomic and exclusive: a crash cannot publish a partial systemd override.
INSTALL_DROPIN_CODE = '''from pathlib import Path
import os,sys,tempfile
p=Path(sys.argv[2]); p.parent.mkdir(parents=True,exist_ok=True)
fd,name=tempfile.mkstemp(prefix='.ledger-',dir=p.parent)
try:
 with os.fdopen(fd,'wb') as stream:
  stream.write(Path(sys.argv[1]).read_bytes()); stream.flush(); os.fsync(stream.fileno())
 os.chmod(name,0o600)
 os.link(name,p)
finally:
 os.unlink(name)
'''


def run(args, *, env=None, cwd=None, timeout=60):
    result=subprocess.run(args,env=env,cwd=cwd,capture_output=True,text=True,timeout=timeout)
    if result.returncode:
        raise RuntimeError('A prerequisite/acceptance command failed. No raw process output is printed; inspect the named service locally.')
    return result.stdout.strip()


def confirm(message):
    return input(message+' [y/N] ').strip().lower()=='y'


def private_write(path,content,*,replace=False):
    """Atomic, private, backed up; never follows a destination symlink."""
    path=Path(path)
    if path.is_symlink():raise RuntimeError('Refusing a symlink configuration destination')
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if path.exists():
        if path.read_text()==content:return False
        if not replace:raise RuntimeError('Existing configuration differs; it was not overwritten')
        backup=path.with_name(path.name+'.backup-'+str(time.time_ns()))
        shutil.copyfile(path,backup);os.chmod(backup,0o600)
    fd,name=tempfile.mkstemp(prefix='.ledger-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:stream.write(content);stream.flush();os.fsync(stream.fileno())
        os.chmod(name,0o600);os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)
    return True


def merge_profile(existing,profile):
    if not isinstance(existing,list):raise RuntimeError('Profile file must contain a JSON array')
    rows=[row for row in existing if row.get('id')==profile['id']]
    if rows:
        if len(rows)!=1 or rows[0]!=profile:raise RuntimeError('Existing mt5-live profile differs; no profile was replaced')
        return existing
    return existing+[profile]


def choose(prefix,filename,explicit=None):
    paths=[Path(explicit).expanduser().resolve()] if explicit else sorted(prefix.glob('drive_c/**/'+filename))
    paths=[p.resolve() for p in paths if p.is_file() and p.resolve().is_relative_to(prefix.resolve())]
    if filename=='python.exe':paths=[p for p in paths if 'Python311' in str(p) and 'Scripts' not in p.parts]
    if len(paths)==1:return paths[0]
    raise RuntimeError('Missing or ambiguous '+filename+' in the LIVE prefix. Install Windows Python 3.11 there, or pass --windows-python / --terminal explicitly.')


def prerequisites(args):
    if sys.platform!='linux' or os.geteuid()==0:raise RuntimeError('Run as the Fedora desktop user, not root')
    prefix=Path.home()/'.mt5-live'
    if not prefix.is_dir():raise RuntimeError('LIVE Wine prefix is missing; DEMO was not touched')
    if prefix.is_symlink() or prefix.resolve()==(Path.home()/'.mt5').resolve():
        raise RuntimeError('LIVE must use its own real Wine prefix, not an alias of DEMO')
    wine=shutil.which('wine')
    if not wine:raise RuntimeError('Wine is not installed')
    python=choose(prefix,'python.exe',args.windows_python)
    terminal=choose(prefix,'terminal64.exe',args.terminal)
    backend_python=ROOT/'backend/.venv/bin/python'
    if not backend_python.is_file():raise RuntimeError('Ledger backend virtual environment is missing')
    env={**os.environ,'WINEPREFIX':str(prefix),'WINEDEBUG':'-all','PYTHONDONTWRITEBYTECODE':'1'}
    return prefix,wine,python,terminal,backend_python,env


def unit(configdir,prefix,wine):
    return f'''[Unit]
Description=Ledger LIVE MT5 read-only bridge
After=graphical-session.target network.target
PartOf=graphical-session.target
StartLimitIntervalSec=300
StartLimitBurst=3

[Service]
Type=simple
Environment=WINEPREFIX={prefix}
Environment=WINEDEBUG=-all
Environment=PYTHONDONTWRITEBYTECODE=1
EnvironmentFile={configdir}/service.env
WorkingDirectory={configdir}/runtime
ExecStart={wine} ${{WINE_PYTHON}} -B -m app.brokers.mt5_bridge_server --config ${{BRIDGE_CONFIG_WINDOWS}}
Restart=on-failure
RestartSec=10
TimeoutStopSec=15
KillMode=control-group
NoNewPrivileges=true
UMask=0077
MemoryMax=1G
TasksMax=256
LimitNOFILE=1024

[Install]
WantedBy=graphical-session.target
'''


def validate_installed(configdir,backend_python):
    config=json.loads((configdir/'bridge.json').read_text())
    if config.get('environment')!='live' or config.get('port')!=18766:raise RuntimeError('Installed LIVE identity/port configuration is invalid')
    listeners=run(['ss','-ltnH','sport = :18766'])
    rows=[line.split() for line in listeners.splitlines() if line.strip()]
    if not rows or any(len(row)<4 or row[3]!='127.0.0.1:18766' for row in rows):
        raise RuntimeError('LIVE bridge is not exclusively listening on IPv4 loopback port 18766')
    result=json.loads(run([str(backend_python),'tools/check_mt5_bridge.py','--confirm-live-read-only',
        '--bridge-url','http://127.0.0.1:18766','--token-file',str(configdir/'token')],cwd=ROOT/'backend',timeout=600))
    if result.get('environment')!='live' or result.get('orders_sent') is not False or result.get('existing_database_touched') is not False:
        raise RuntimeError('Read-only acceptance did not confirm its safety contract')
    print('LIVE read-only connection and repeated Journal import passed in a NEW temporary database.')
    print(json.dumps({key:result.get(key) for key in ('environment','first_sync','repeat_sync','journal_trades')},indent=2))


def backend_configuration(backend_python,configdir):
    # Read configuration only. Import no services, open no database, print no credentials.
    probe="from app.core.config import Settings; from app.brokers.profiles import profiles; import json; s=Settings(); print(json.dumps({'overlay':s.broker_profiles_file,'ids':[p.id for p in profiles(s)],'inline_ids':[p.get('id') for p in json.loads(s.broker_profiles_json or '[]')]}))"
    settings=json.loads(run([str(backend_python),'-c',probe],cwd=ROOT/'backend'))
    target=configdir/'profiles.json'
    if settings['overlay'] and Path(settings['overlay']).resolve()!=target.resolve():
        raise RuntimeError('A different BROKER_PROFILES_FILE is already configured. No profile file was replaced; merge mt5-live into that existing overlay explicitly.')
    if 'mt5-live' in settings['inline_ids'] or ('mt5-live' in settings['ids'] and not target.exists()):
        raise RuntimeError('An mt5-live profile already exists outside the managed overlay; it was preserved')
    user=subprocess.run(['systemctl','--user','cat','ledger-backend.service'],capture_output=True,text=True)
    scope=['--user'] if user.returncode==0 else []
    text=user.stdout if scope else run(['systemctl','cat','ledger-backend.service'])
    marker='# Managed Ledger LIVE read-only profile overlay'
    if 'BROKER_PROFILES_FILE' in text and marker not in text:
        raise RuntimeError('Existing backend service defines a profile overlay. No systemd override was changed')
    if marker in text and 'Environment="BROKER_PROFILES_FILE='+str(target)+'"' not in text:
        raise RuntimeError('Managed backend override differs; no existing override was changed')
    return scope,text,marker


def main():
    parser=argparse.ArgumentParser()
    modes=parser.add_mutually_exclusive_group(required=True)
    for mode in ('check','install','validate'):modes.add_argument('--'+mode,action='store_true')
    parser.add_argument('--windows-python');parser.add_argument('--terminal')
    args=parser.parse_args()
    prefix,wine,python,terminal,backend_python,env=prerequisites(args)
    configdir=Path.home()/'.config/ledger-mt5-live-bridge'
    if args.check:
        print('LIVE prefix, Windows Python 3.11, terminal executable and backend venv found.')
        print('Read-only file preflight only: no Wine process started, account contacted, service changed or database opened.')
        print('Install verifies the official MetaTrader5 package and actual LIVE identity before writing configuration.')
        return
    if args.validate:
        validate_installed(configdir,backend_python);return
    backend_scope,backend_text,marker=backend_configuration(backend_python,configdir)
    if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
        raise RuntimeError('Log into KDE first; Wine terminal operation needs the desktop session')
    active=subprocess.run(['systemctl','--user','is-active','--quiet',SERVICE]).returncode==0
    if not active:
        with socket.socket() as sock:
            try:sock.bind(('127.0.0.1',18766))
            except OSError:raise RuntimeError('Port 18766 is occupied; no process was stopped') from None
    terminal_windows=run(['winepath','-w',str(terminal)],env=env)
    probe='''import json,sys
import MetaTrader5 as m
assert m.initialize(sys.argv[1],timeout=30000)
try:
 a=m.account_info();t=m.terminal_info()
 assert a is not None and t is not None and t.connected and a.trade_mode==2
 print(json.dumps(dict(login=a.login,server=a.server,mode=a.trade_mode,version=m.__version__)))
finally:m.shutdown()
'''
    try:identity=json.loads(run([wine,str(python),'-c',probe,terminal_windows],env=env))
    except Exception:
        print('Verify LIVE login and install the official MetaTrader5 package in LIVE Windows Python if missing.')
        print('Use WINEPREFIX="$HOME/.mt5-live" wine <LIVE-python.exe> -m pip install MetaTrader5==5.0.6231')
        raise RuntimeError('LIVE identity/package preflight failed; no configuration was written') from None
    if not confirm('Confirm LIVE read-only account ending '+str(identity['login'])[-4:]+' on server '+identity['server']):return
    # Existing live services are never silently restarted mid-sync.
    if active and not confirm('Restart ONLY the LIVE read-only bridge after configuration checks?'):return
    configdir.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(configdir,0o700)
    token=configdir/'token'
    if not token.exists():private_write(token,secrets.token_urlsafe(48)+'\n')
    if token.is_symlink() or len(token.read_text().strip())<32:raise RuntimeError('Invalid private LIVE token file')
    demo_config=Path.home()/'.config/ledger-mt5-bridge'
    for candidate in demo_config.glob('*token*'):
        if candidate.is_file() and candidate.stat().st_size<4096 and candidate.read_text().strip()==token.read_text().strip():
            raise RuntimeError('LIVE token must be independent of the DEMO token')
    os.chmod(token,0o600)
    config=dict(environment='live',allow_initialize=True,expected_login=identity['login'],expected_server=identity['server'],
                expected_trade_mode=2,terminal_path=terminal_windows,timestamp_policy='unverified',port=18766,
                token_file=run(['winepath','-w',str(token)],env=env))
    private_write(configdir/'bridge.json',json.dumps(config,indent=2)+'\n')
    for name in ('__init__.py','brokers/__init__.py','brokers/mt5_bridge_server.py','brokers/mt5_bridge_protocol.py'):
        source=ROOT/'backend/app'/name
        content=source.read_text() if name.endswith(('mt5_bridge_server.py','mt5_bridge_protocol.py')) else ''
        private_write(configdir/'runtime/app'/name,content,replace=True)
    environment='WINE_PYTHON='+json.dumps(str(python))+'\nBRIDGE_CONFIG_WINDOWS='+json.dumps(run(['winepath','-w',str(configdir/'bridge.json')],env=env))+'\n'
    private_write(configdir/'service.env',environment)
    servicepath=Path.home()/'.config/systemd/user'/SERVICE
    private_write(servicepath,unit(configdir,prefix,wine))
    run(['systemctl','--user','daemon-reload'])
    run(['systemctl','--user','restart' if active else 'start',SERVICE])
    time.sleep(3)
    try:validate_installed(configdir,backend_python)
    except Exception:
        if not active:run(['systemctl','--user','stop',SERVICE])
        raise
    # Additive overlay: never rewrite .env or the existing JSON environment value.
    profile=dict(id='mt5-live',provider='mt5',environment='live',enabled=True,
                 credentials=dict(bridge_url='http://127.0.0.1:18766',bridge_token_file=str(token)))
    profilepath=configdir/'profiles.json'
    existing=json.loads(profilepath.read_text()) if profilepath.exists() else []
    private_write(profilepath,json.dumps(merge_profile(existing,profile),indent=2)+'\n',replace=True)
    content=marker+'\n[Service]\nEnvironment="BROKER_PROFILES_FILE='+str(profilepath)+'"\n'
    if backend_scope:
        dropin=Path.home()/'.config/systemd/user/ledger-backend.service.d/90-mt5-live-profile.conf'
        private_write(dropin,content)
    elif marker not in backend_text:
        pending=configdir/'backend-profile.conf';private_write(pending,content)
        print('Backend is a system-level service; installing its NEW drop-in requires sudo. No restart will occur.')
        if not confirm('Install the additive system-service drop-in?'):
            print('Bridge accepted, backend profile activation remains pending. Re-run --install when ready.');return
        target='/etc/systemd/system/ledger-backend.service.d/90-mt5-live-profile.conf'
        # Exclusive creation protects existing overrides, including a concurrent install.
        if subprocess.run(['sudo','python3','-c',INSTALL_DROPIN_CODE,str(pending),target]).returncode:
            raise RuntimeError('System drop-in was not installed; any existing override was preserved')
    command=['systemctl',*backend_scope,'daemon-reload']
    if not backend_scope:command=['sudo',*command]
    if subprocess.run(command).returncode:raise RuntimeError('systemd reload failed; backend was not restarted')
    print('LIVE profile overlay installed. Backend was NOT restarted; finish active work, then restart ledger-backend.service yourself.')
    print('After that planned restart, the accepted LIVE profile is enabled and the existing scheduler defaults to read-only auto-sync. Settings can disable it.')
    print('Settings -> mt5-live -> Test/discover / Sync now verifies the active backend. No account login switch is performed.')
    if confirm('Acceptance passed. Enable ONLY the LIVE bridge after future KDE logins?'):
        run(['systemctl','--user','enable',SERVICE])
    print('DEMO service, Telegram bot, .env and existing Ledger database were not modified.')


if __name__=='__main__':
    try:main()
    except (Exception,KeyboardInterrupt) as exc:
        # Only our own constant RuntimeError messages are operator-safe.
        print(str(exc) if type(exc) is RuntimeError else 'Installation stopped safely; configuration backups are retained.',file=sys.stderr)
        sys.exit(1)
