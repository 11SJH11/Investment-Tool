"""Executed only by explicit workspace actions, never by plugin discovery."""
import contextlib
from dataclasses import asdict
import inspect
import io
import json
from pathlib import Path
import sys
import traceback
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class CapturedOutput(io.TextIOBase):
    def __init__(self): self.characters = 0
    def write(self, text):
        self.characters += len(text)
        return len(text)
    def flush(self): pass


def execute(job):
    from app.backtesting.strategies import strategy_registry
    from app.backtesting.strategies.base import Strategy, StrategySpec
    before = {s.key for s in strategy_registry.specs()}
    module = types.ModuleType('ledger_workspace_draft')
    module.__file__ = job['filename']
    sys.modules[module.__name__] = module
    exec(compile(job['source'], job['filename'], 'exec'), module.__dict__)
    classes = [cls for cls in vars(module).values() if inspect.isclass(cls)
               and cls is not Strategy and issubclass(cls, Strategy) and cls.__module__ == module.__name__]
    if len(classes) != 1:
        return {'ok': False, 'message': 'Exactly one Strategy subclass is required.'}
    cls = classes[0]
    if not isinstance(getattr(cls,'spec',None), StrategySpec):
        return {'ok': False, 'message': 'The strategy must define a StrategySpec.'}
    if cls.spec.key != job['key']:
        return {'ok': False, 'message': f"StrategySpec.key must be {job['key']}"}
    if not cls.spec.timeframes or any(tf not in {'1m','5m','15m','30m','1h','4h','1d'} for tf in cls.spec.timeframes):
        return {'ok': False, 'message': 'Declare supported timeframes: 1m, 5m, 15m, 30m, 1h, 4h or 1d.'}
    if cls.on_bar is Strategy.on_bar or inspect.iscoroutinefunction(cls.on_bar):
        return {'ok': False, 'message': 'Override synchronous on_bar(self, ctx).'}
    instance = cls(); instance.reset()
    inspect.signature(instance.on_bar).bind(object())
    added = {s.key for s in strategy_registry.specs()} - before
    if not added:
        strategy_registry.register(cls)
    elif added != {job['key']} or type(strategy_registry.create(job['key'])) is not cls:
        raise ValueError('Unexpected strategy registration')
    result = {'ok': True, 'message': 'Strategy interface valid.', 'strategy': asdict(cls.spec)}
    if job['action'] == 'tests':
        tests = [(name,fn) for name,fn in vars(module).items() if name.startswith('test_') and inspect.isfunction(fn) and fn.__module__ == module.__name__]
        if not tests:
            return {'ok': False, 'message': 'No test_ functions found. Add zero-argument deterministic tests.'}
        results = []
        for name,fn in sorted(tests):
            try:
                returned = fn()
                if inspect.isawaitable(returned):
                    returned.close()
                    raise ValueError('Async tests are not supported')
                results.append({'name':name, 'passed':True})
            except Exception as exc:
                results.append({'name':name, 'passed':False, 'error_type':type(exc).__name__})
        result.update(ok=all(t['passed'] for t in results), tests=results,
                      message=f"{sum(t['passed'] for t in results)}/{len(results)} strategy tests passed.")
    elif job['action'] == 'backtest':
        from app.core.config import Settings
        from app.services.container import build_services
        services = build_services(Settings(_env_file=None, **job['settings']))
        try:
            result['result'] = services.backtest.run(job['payload'])
            result['message'] = 'Backtest completed using the common engine.'
        finally:
            services.close()
    return result


def main():
    output = CapturedOutput(); errors = CapturedOutput()
    try:
        job = json.load(sys.stdin)
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            result = execute(job)
    except BaseException as exc:
        frames = traceback.extract_tb(exc.__traceback__)
        location = next((f for f in reversed(frames) if f.filename.startswith('_workspace_')), None)
        result = {'ok': False, 'message': 'Execution failed. Exception text withheld to protect credentials.',
                  'error_type': type(exc).__name__, 'line': location.lineno if location else None}
    result['output'] = {'stdout_characters': output.characters, 'stderr_characters': errors.characters,
                        'message': 'Output captured and withheld to protect credentials.'}
    print('LEDGER_WORKSPACE_RESULT:' + json.dumps(result, default=str, allow_nan=False))


if __name__ == '__main__': main()
