"""Install/update only a Ledger-owned user worker unit; never start services or open a DB.

Default is a read-only plan. A worker entry point must already exist and be runnable
with ``python -m``. This installer does not turn diagnostic code into execution code.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

MARKER = '# Managed by Ledger install_algo_worker.py v1\n'


def quote(value):
    text = str(value)
    if '$' in text or any(ord(c) < 32 for c in text):
        raise ValueError('Control characters and dollar substitutions are not allowed in service paths')
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'


def plan(root, name, module, config, state):
    root, config, state = (Path(p).expanduser().resolve() for p in (root, config, state))
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', name):
        raise ValueError('Invalid worker name')
    if not re.fullmatch(r'app\.forward\.[a-z][a-z0-9_]*', module):
        raise ValueError('Only an explicit app.forward worker entry point is supported')
    backend = root/'backend'
    source = backend.joinpath(*module.split('.')).with_suffix('.py')
    python = backend/'.venv/bin/python'
    if not source.is_file() or not source.resolve().is_relative_to(backend.resolve()) or not python.is_file():
        raise ValueError('Worker module or existing backend virtual environment is missing')
    # No imports: importing a worker can initialize services, data or broker clients.
    if '__main__' not in source.read_text(encoding='utf-8'):
        raise ValueError('Module has no command-line entry point; worker implementation is not deployable yet')
    if not config.is_file():
        raise ValueError('Explicit worker configuration file is required; no .env is inferred')
    if config.name == '.env':
        raise ValueError('Use a dedicated worker configuration, not the backend .env')
    if os.name == 'posix' and config.stat().st_mode & 0o077:
        raise ValueError('Worker configuration must be private (chmod 600)')
    if state == root or state.is_relative_to(root) or root.is_relative_to(state):
        raise ValueError('Worker state must be a separate directory outside the repository')
    if config.is_relative_to(state):
        raise ValueError('Configuration must not be writable by the worker')
    if state.exists() and (not state.is_dir() or any(state.iterdir())):
        # Updates can use an existing non-empty directory only when already marked
        # by this installer. No discovery or adoption of production databases.
        marker = state/'.ledger-algo-state'
        if not marker.is_file() or marker.read_text() != name:
            raise ValueError('Refusing to adopt an existing data directory')
    service = 'ledger-algo-' + name + '.service'
    unit = MARKER + f'''[Unit]
Description=Ledger isolated algorithm worker ({name})
After=network.target
StartLimitIntervalSec=300
StartLimitBurst=3

[Service]
Type=simple
WorkingDirectory={quote(backend)}
ExecStart={quote(python)} -B -m {module} --config {quote(config)} --state-directory {quote(state)}
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=PYTHONUNBUFFERED=1
Restart=no
TimeoutStopSec=30
KillMode=control-group
UMask=0077
NoNewPrivileges=true
PrivateUsers=true
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=true
ReadWritePaths={quote(state)}
RestrictSUIDSGID=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
MemoryMax=1G
TasksMax=64
LimitNOFILE=1024

[Install]
WantedBy=default.target
'''
    return service, unit, state


def publish(destination, content, *, replace=False):
    destination = Path(destination)
    if destination.is_symlink():
        raise ValueError('Refusing symlink unit')
    old = destination.read_text() if destination.exists() else None
    if old == content:
        return False
    if old is not None and (not old.startswith(MARKER) or not replace):
        raise ValueError('Existing unit is not ours, or --replace was not supplied')
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.ledger-worker-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        if old is not None:
            backup = destination.with_name(destination.name+'.backup-'+str(time.time_ns()))
            with backup.open('x', encoding='utf-8') as stream:
                stream.write(old)
            os.chmod(backup, 0o600)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    return True


def install(home, service, unit, state, name, *, replace=False, run=subprocess.run):
    home = Path(home)
    target = home/'.config/systemd/user'/service
    # Refuse updates while this worker is active; no automatic restart or stop.
    status = run(['systemctl','--user','show',service,'--property=ActiveState','--value'], capture_output=True, text=True, timeout=15)
    if status.returncode != 0 or status.stdout.strip() not in {'inactive','failed'}:
        raise ValueError('Cannot verify this worker is stopped. Stop only its own unit before updating')
    changed = publish(target, unit, replace=replace)
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = state/'.ledger-algo-state'
    if not marker.exists():
        with marker.open('x', encoding='utf-8') as stream: stream.write(name)
        os.chmod(marker, 0o600)
    if changed:
        # daemon-reload rereads unit files; it does not restart running services.
        result = run(['systemctl','--user','daemon-reload'], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise ValueError('Unit installed, but daemon-reload failed. No service was started')
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--module', required=True)
    parser.add_argument('--config', required=True)
    parser.add_argument('--state-directory', required=True)
    parser.add_argument('--install', action='store_true', help='Explicitly install a stopped unit; never start/enable it')
    parser.add_argument('--replace', action='store_true', help='Back up and replace only a unit managed by this installer')
    args = parser.parse_args()
    if sys.platform != 'linux' or os.geteuid() == 0:
        parser.error('Run on Fedora as the desktop user, not root')
    try:
        service, unit, state = plan(args.root,args.name,args.module,args.config,args.state_directory)
        print(unit)
        if args.install:
            path = install(Path.home(),service,unit,state,args.name,replace=args.replace)
            print('Installed:',path)
        else:
            print('PLAN ONLY: no files or services changed. Pass --install for an approved rollout.')
        print('No service started/enabled/restarted. No database opened or migrated. Existing bridges and Telegram untouched.')
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        parser.exit(1, f'Installation refused: {exc}\n')


if __name__ == '__main__':
    main()
