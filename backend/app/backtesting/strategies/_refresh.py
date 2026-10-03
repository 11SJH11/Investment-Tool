"""Atomic manual loading of trusted local strategy source; not a code sandbox."""
from contextlib import contextmanager
from dataclasses import asdict
from functools import wraps
from hashlib import sha256
import importlib
import importlib.abc
import importlib.util
import inspect
import json
from pathlib import Path
import sys
from threading import RLock

from .base import Strategy, StrategySpec, ParameterSpec


class RefreshBusy(ValueError):
    pass


def execution_scope(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        from .registry import strategy_registry
        with strategy_registry.executing():
            return function(*args, **kwargs)
    return wrapped


class Sources(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, package, root, sources):
        self.package, self.root, self.sources = package, root, sources

    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(self.package + '.'):
            name = fullname[len(self.package)+1:] + '.py'
            if name in self.sources:
                return importlib.util.spec_from_loader(fullname, self, origin=str(self.root/name))

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        name = module.__name__[len(self.package)+1:] + '.py'
        module.__file__ = str(self.root/name)
        exec(compile(self.sources[name], module.__file__, 'exec'), module.__dict__)


class RefreshSupport:
    def _init_refresh(self):
        self._lock = RLock()
        self._active = 0
        self._candidate = None
        self._sources = {}
        self._package = 'app.backtesting.strategies'
        self._root = Path(__file__).parent

    @contextmanager
    def executing(self):
        with self._lock:
            self._active += 1
        try:
            yield
        finally:
            with self._lock:
                self._active -= 1

    def sources(self):
        with self._lock:
            return dict(self._sources)

    def provenance(self, key):
        with self._lock:
            return dict(getattr(self._items[key], 'implementation_provenance', {}))

    @staticmethod
    def _validate(cls):
        if not isinstance(cls, type) or not issubclass(cls, Strategy) or not isinstance(cls.spec, StrategySpec):
            raise ValueError('Expected Strategy subclass with StrategySpec')
        spec = cls.spec
        if not isinstance(spec.key, str) or not spec.key.strip() or not isinstance(spec.name, str) or not spec.name.strip():
            raise ValueError('StrategySpec requires a nonempty key and name')
        if not spec.timeframes or any(tf not in {'1m','5m','15m','30m','1h','4h','1d'} for tf in spec.timeframes):
            raise ValueError('StrategySpec has invalid timeframes')
        if not isinstance(spec.defaults, dict):
            raise ValueError('StrategySpec defaults must be a mapping')
        parameters = (*spec.parameters, *spec.research_parameters)
        if any(not isinstance(p, ParameterSpec) or p.kind not in {'int','float','bool','choice','string'} for p in parameters):
            raise ValueError('StrategySpec has invalid parameters')
        if len({p.key for p in parameters}) != len(parameters):
            raise ValueError('StrategySpec contains duplicate parameter keys')
        json.dumps(asdict(spec), allow_nan=False)
        if cls.on_bar is Strategy.on_bar:
            raise ValueError('Strategy must implement on_bar(ctx)')
        inspect.signature(cls.on_bar).bind(None, None)
        instance = cls()
        instance.reset()

    def refresh(self, *, sources=None):
        with self._lock:
            if self._active:
                raise RefreshBusy('Strategies are in use. Wait for active backtests/research jobs to finish, then refresh.')
            package, root = self._package, self._root
            if sources is None:
                sources = {}
                for path in sorted(root.glob('*.py')):
                    if path.name.startswith('_') or path.name in {'base.py','registry.py'}:
                        continue
                    if path.is_symlink():
                        return {'ok':False, 'errors':[{'module':path.name, 'message':'Symlink strategy modules are not supported'}]}
                    try:
                        sources[path.name] = path.read_bytes()
                    except OSError:
                        return {'ok':False, 'errors':[{'module':path.name, 'message':'Cannot read strategy source'}]}
            manifest = {name:sha256(source).hexdigest() for name,source in sources.items()}
            digest = sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
            names = {package+'.'+name[:-3] for name in {*self._sources, *sources}}
            old_modules = {name:sys.modules[name] for name in names if name in sys.modules}
            parent = sys.modules[package]
            old_attrs = {name.rsplit('.',1)[1]:getattr(parent,name.rsplit('.',1)[1]) for name in names if hasattr(parent,name.rsplit('.',1)[1])}
            for name in names:
                sys.modules.pop(name, None)
                parent.__dict__.pop(name.rsplit('.',1)[1], None)
            loader = Sources(package,root,sources)
            importlib.invalidate_caches()
            sys.meta_path.insert(0,loader)
            self._candidate = {}
            errors = []
            committed = False
            try:
                for filename in sorted(sources):
                    try:
                        importlib.import_module(package+'.'+filename[:-3])
                    except (Exception, SystemExit) as exc:
                        # Plugin exception messages may contain credentials. Report
                        # module/type/line, with actionable validation categories.
                        message = str(exc) if isinstance(exc, RegistryValidationError) else type(exc).__name__
                        if isinstance(exc,SyntaxError): message += f' at line {exc.lineno}: {exc.msg}'
                        if isinstance(exc,ModuleNotFoundError): message += f': missing module {exc.name}'
                        errors.append({'module':filename,'message':message})
                for key, cls in self._candidate.items():
                    try:
                        self._validate(cls)
                    except Exception as exc:
                        errors.append({'module':cls.__module__.rsplit('.',1)[-1]+'.py',
                                       'message':f'Invalid strategy {key}: {type(exc).__name__}; check StrategySpec, constructor/reset and on_bar(ctx)'})
                if errors:
                    return {'ok':False, 'errors':errors}
                for key, cls in self._candidate.items():
                    filename = cls.__module__.rsplit('.',1)[-1]+'.py'
                    cls.implementation_provenance = dict(key=key,module=cls.__module__,class_name=cls.__name__,
                        source_sha256=manifest.get(filename), registry_sha256=digest)
                old = {key:self.provenance(key) for key in self._items}
                added = len(self._candidate.keys()-self._items.keys())
                removed = len(self._items.keys()-self._candidate.keys())
                updated = sum(old[key].get('source_sha256') != cls.implementation_provenance['source_sha256']
                              for key,cls in self._candidate.items() if key in old)
                self._items = self._candidate
                self._sources = dict(sources)
                committed = True
                return {'ok':True,'added':added,'updated':updated,'removed':removed,'errors':[]}
            finally:
                sys.meta_path.remove(loader)
                self._candidate = None
                if not committed:
                    for name in names:
                        sys.modules.pop(name,None)
                        parent.__dict__.pop(name.rsplit('.',1)[1],None)
                    sys.modules.update(old_modules)
                    parent.__dict__.update(old_attrs)


class RegistryValidationError(ValueError):
    pass
