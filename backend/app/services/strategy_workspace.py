"""Local trusted-code workspace. Reading, saving and syntax checks never import drafts."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import importlib.util
from datetime import datetime, timezone


STRATEGIES = Path(__file__).resolve().parents[1] / 'backtesting' / 'strategies'
PREFIX = '_workspace_'
MAX_SOURCE = 100_000
_SAVE_LOCK = threading.Lock()


def revision(source):
    return hashlib.sha256(source.encode('utf-8')).hexdigest()


def syntax(source):
    if len(source.encode('utf-8')) > MAX_SOURCE:
        raise ValueError('Strategy source exceeds 100 KB')
    try:
        ast.parse(source)
        return {'ok': True, 'message': 'Syntax valid. No code executed.'}
    except SyntaxError as exc:
        return {'ok': False, 'message': exc.msg, 'line': exc.lineno, 'column': exc.offset}


def template(slug='my_strategy'):
    return f'''from app.backtesting.strategies.base import Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry
from app.backtesting.models import EntrySignal

@strategy_registry.register
class MyStrategy(Strategy):
    spec = StrategySpec(key="workspace_{slug}", name="My strategy", timeframes=("5m",))

    def on_bar(self, ctx):
        # Only completed bars are visible. Return EntrySignal with a structural stop.
        # The common engine owns next-bar fills, sizing, costs and accounting.
        return None

def test_strategy():
    strategy = MyStrategy()
    assert strategy.spec.timeframes == ("5m",)
'''


class StrategyWorkspace:
    def __init__(self, root=STRATEGIES, *, timeout=15):
        self.root = Path(root).resolve()
        self.timeout = timeout

    def _path(self, filename, *, writing=False):
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,79}\.py|_workspace_[a-z][a-z0-9_]{0,63}\.py', filename):
            raise ValueError('Use a lowercase Python filename; paths are not allowed')
        if writing and not re.fullmatch(r'_workspace_[a-z][a-z0-9_]{0,63}\.py', filename):
            raise ValueError('Built-in files are read-only. Save a copy as _workspace_name.py')
        path = self.root / filename
        if path.is_symlink() or path.resolve().parent != self.root:
            raise ValueError('Strategy path is outside the workspace')
        if filename in {'base.py', 'registry.py'}:
            raise ValueError('Strategy infrastructure is not editable')
        return path

    def list(self):
        return {'files': [{'filename': p.name, 'read_only': not p.name.startswith(PREFIX)}
                          for p in sorted(self.root.glob('*.py'))
                          if p.name not in {'__init__.py', 'base.py', 'registry.py'} and not p.is_symlink()],
                'template': template(), 'default_filename': '_workspace_my_strategy.py',
                'activations': self._activations()}

    def _activations(self):
        path = self.root / '.workspace-activations.json'
        if path.is_symlink():
            raise ValueError('Unsafe activation manifest')
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}

    def _write_activations(self, values):
        target = self.root / '.workspace-activations.json'
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.root, delete=False, suffix='.tmp') as stream:
            temporary = Path(stream.name)
            json.dump(values, stream)
        try: os.replace(temporary, target)
        finally: temporary.unlink(missing_ok=True)

    def activate(self, filename, source, *, trusted=False, services=None):
        from app.backtesting.strategies import strategy_registry
        if not trusted:
            raise ValueError('Activation requires explicit trusted local-code acknowledgement')
        self._path(filename, writing=True)
        key = filename.removesuffix('.py').removeprefix('_')
        with _SAVE_LOCK:
            if self.read(filename)['source'] != source:
                raise ValueError('Save this exact source before activating')
            if any(spec.key == key for spec in strategy_registry.specs()):
                raise ValueError('Registry key already exists; deactivate your active version before replacing it')
            checked = self.execute('tests', filename, source, trusted=True, services=services)
            if not checked.get('ok'):
                return checked
            promoted = self._path(key + '.py')
            if promoted.exists():
                raise ValueError('Activation would overwrite an existing module')
            metadata = {'filename': filename, 'source_sha256': revision(source),
                        'version': revision(source)[:12], 'activated_at': datetime.now(timezone.utc).isoformat()}
            generated = source + '\nfrom app.backtesting.strategies.registry import strategy_registry as _ledger_registry\n'
            generated += f'_ledger_registry.register_workspace_class({checked["class_name"]}, {metadata!r})\n'
            history = self.root / '_workspace_history'
            if history.is_symlink():
                raise ValueError('Unsafe workspace history directory')
            history.mkdir(exist_ok=True)
            history_file = history / (revision(source) + '.py')
            if history_file.is_symlink():
                raise ValueError('Unsafe workspace history file')
            if not history_file.exists():
                history_file.write_text(source, encoding='utf-8')
            # A unique new module is discoverable on the next startup, too.
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.root, suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(generated)
            try: os.replace(temporary, promoted)
            finally: temporary.unlink(missing_ok=True)
            module_name = 'app.backtesting.strategies.' + key
            try:
                spec = importlib.util.spec_from_file_location(module_name, promoted)
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                activations = self._activations()
                activations[filename] = {**metadata, 'key': key, 'module': promoted.name,
                    'module_sha256': revision(generated), 'active': True}
                self._write_activations(activations)
            except Exception:
                existing = strategy_registry._items.get(key)
                if existing and existing.__module__ == module_name:
                    del strategy_registry._items[key]
                promoted.unlink(missing_ok=True)
                sys.modules.pop(module_name, None)
                raise ValueError('Activation failed; source history preserved. Exception details withheld.') from None
            return {'ok': True, 'message': 'Activated. Select this strategy in Backtest.', 'activation': activations[filename]}

    def deactivate(self, filename):
        from app.backtesting.strategies import strategy_registry
        self._path(filename, writing=True)
        with _SAVE_LOCK:
            activations = self._activations()
            item = activations.get(filename)
            if not item or not item.get('active'):
                raise ValueError('This draft has no active strategy')
            promoted = self._path(item['module'])
            if not promoted.name.startswith('workspace_') or revision(promoted.read_text(encoding='utf-8')) != item['module_sha256']:
                raise ValueError('Promoted module changed; refusing to delete it')
            strategy_registry.deactivate_workspace(item['key'], item['source_sha256'])
            promoted.unlink()
            sys.modules.pop('app.backtesting.strategies.' + item['key'], None)
            item['active'] = False
            self._write_activations(activations)
            return {'ok': True, 'message': 'Deactivated. Draft and immutable source history retained.'}

    def read(self, filename):
        path = self._path(filename)
        if not path.is_file():
            raise ValueError('Strategy file not found')
        if path.stat().st_size > MAX_SOURCE:
            raise ValueError('Strategy source exceeds 100 KB')
        source = path.read_text(encoding='utf-8')
        return {'filename': filename, 'source': source, 'revision': revision(source),
                'read_only': not filename.startswith(PREFIX)}

    def save(self, filename, source, expected_revision=None):
        path = self._path(filename, writing=True)
        result = syntax(source)
        if not result['ok']:
            return result
        with _SAVE_LOCK:
            if path.exists() and self.read(filename)['revision'] != expected_revision:
                raise ValueError('File changed or already exists. Reload before overwriting it')
            if not path.exists() and expected_revision is not None:
                raise ValueError('File was removed. Save as a new file')
            self.root.mkdir(parents=True, exist_ok=True)
            # Atomic replace prevents a partial draft from being mistaken for a saved version.
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.root,
                                             prefix='.workspace-', suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(source)
            try:
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        return {'ok': True, **self.read(filename), 'message': 'Saved without executing code.'}

    def execute(self, action, filename, source, *, trusted=False, services=None, payload=None):
        self._path(filename, writing=True)
        if not trusted:
            raise ValueError('Explicit trusted local-code acknowledgement is required')
        if action not in {'interface', 'tests', 'backtest'}:
            raise ValueError('Unknown workspace action')
        checked = syntax(source)
        if not checked['ok']:
            return checked
        key = filename.removesuffix('.py').removeprefix('_')
        job = {'action': action, 'source': source, 'filename': filename, 'key': key}
        if action == 'backtest':
            if services is None:
                raise ValueError('Backtest services are required')
            # Credentials travel only through the private stdin pipe, never command arguments/files.
            values = services.settings.model_dump(mode='json')
            settings = {field.validation_alias or key: values[key]
                        for key,field in type(services.settings).model_fields.items()}
            settings['LEDGER_DATA_DIR'] = str(services.settings.data_dir.resolve())
            job.update(settings=settings, payload={**(payload or {}), 'strategy_key': key, 'save_run': False})
        result = _run_worker(job, timeout=120 if action == 'backtest' else self.timeout)
        if services is not None:
            result = _redact(result, services.settings.model_dump(mode='json', by_alias=True))
        if result.get('ok') and action == 'backtest':
            run = result['result']
            run['workspace'] = {'filename': filename, 'source_sha256': revision(source)}
            if (payload or {}).get('save_run', True):
                snapshot = _redact(job['payload'], services.settings.model_dump(mode='json'))
                saved = services.backtest_runs.create(
                    config={**snapshot, 'workspace': run['workspace']}, result=run,
                    name=str(snapshot.get('run_name') or filename),
                    notes=str(snapshot.get('run_notes') or ''),
                    test_role=str(snapshot.get('test_role') or 'development'),
                    tags=snapshot.get('run_tags') or [], experiment_group='')
                run['saved_run'] = {k: saved[k] for k in ('id','name','test_role','created_at')}
        return result


def _redact(value, settings):
    secrets = set()
    def collect(data, sensitive=False):
        if isinstance(data, dict):
            for k,v in data.items():
                collect(v, sensitive or bool(re.search(r'key|secret|token|account_id|client_id|password', k, re.I)))
        elif isinstance(data, list):
            for item in data: collect(item, sensitive)
        elif isinstance(data, str):
            if sensitive and data: secrets.add(data)
    collect(settings)
    try: collect(json.loads(settings.get('BROKER_PROFILES_JSON') or settings.get('broker_profiles_json') or '[]'))
    except (TypeError, ValueError): pass
    def clean(item):
        if isinstance(item, str):
            for secret in sorted(secrets, key=len, reverse=True): item = item.replace(secret, '[redacted]')
            return item
        if isinstance(item, dict): return {clean(k):clean(v) for k,v in item.items()}
        if isinstance(item, list): return [clean(v) for v in item]
        return item
    return clean(value)


def _run_worker(job, *, timeout):
    backend = Path(__file__).resolve().parents[2]
    runner = backend / 'app' / 'backtesting' / 'workspace_worker.py'
    env = {k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PATH','TEMP','TMP','LANG'}}
    env['PYTHONIOENCODING'] = 'utf-8'
    with tempfile.TemporaryDirectory(prefix='ledger-workspace-') as cwd:
        process = subprocess.Popen([sys.executable, '-B', str(runner)], cwd=cwd, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        captured = [bytearray(), bytearray()]
        overflow = threading.Event()
        def drain(stream, index):
            while chunk := stream.read(8192):
                if len(captured[index]) + len(chunk) <= 8_000_000:
                    captured[index].extend(chunk)
                else:
                    overflow.set()
        threads = [threading.Thread(target=drain,args=(stream,i),daemon=True)
                   for i,stream in enumerate((process.stdout,process.stderr))]
        for thread in threads: thread.start()
        try:
            process.stdin.write(json.dumps(job).encode('utf-8')); process.stdin.close()
            process.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, BrokenPipeError):
            if os.name == 'nt':
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            process.kill(); process.wait()
            return {'ok': False, 'message': 'Worker timed out or exited before accepting the request.'}
        finally:
            for thread in threads: thread.join(timeout=2)
        if overflow.is_set():
            return {'ok': False, 'message': 'Worker output exceeded the 8 MB limit.'}
        # Never expose raw process output, tracebacks or exception text.
        try:
            lines = captured[0].decode('utf-8').splitlines()
            line = next(line for line in reversed(lines) if line.startswith('LEDGER_WORKSPACE_RESULT:'))
            result = json.loads(line.removeprefix('LEDGER_WORKSPACE_RESULT:'))
            if not isinstance(result, dict): raise ValueError()
            return result
        except (ValueError, StopIteration):
            return {'ok': False, 'message': 'Worker failed; raw output withheld to protect credentials.'}
