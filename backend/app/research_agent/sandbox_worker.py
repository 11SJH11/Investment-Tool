"""Container-only entry point. Never import this module in the Ledger server."""
import os
import sys


def main():
    import contextlib
    from dataclasses import asdict
    from datetime import datetime
    import types
    import importlib.abc
    import importlib.util
    import re
    import pandas as pd
    from app.backtesting.context import StrategyContext
    from app.backtesting.models import Position
    from app.backtesting.strategies.base import Strategy, StrategySpec
    from app.research_agent.sandbox_wire import decode, encode, signal_to_json, MAX_MESSAGE
    from app.backtesting.strategies import strategy_registry
    # Protocol output is bounded by the host. Arbitrary stdout is never a log or an instruction.
    protocol = sys.stdout.buffer
    incoming = sys.stdin.buffer
    strategy = None
    histories = {}
    for raw in iter(lambda: incoming.readline(MAX_MESSAGE+1), b''):
        try:
            message = decode(raw, MAX_MESSAGE)
            with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                if message['op'] == 'init':
                    if strategy is not None: raise ValueError('Already initialized')
                    modules=message.get('modules',{})
                    if (not isinstance(modules,dict) or len(modules)>32 or
                        any(not isinstance(k,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*\.py',k)
                            or k in {'base.py','registry.py','__init__.py'} or k.startswith('__')
                            or not isinstance(v,str) for k,v in modules.items()) or
                        sum(len(v.encode()) for v in modules.values())>50000):
                        raise ValueError('Invalid archived dependency bundle')
                    # In-memory, process-local archived modules only. Never mounted
                    # from the repository or installed into the host registry.
                    class ArchivedLoader(importlib.abc.MetaPathFinder,importlib.abc.Loader):
                        def find_spec(self,fullname,path=None,target=None):
                            prefix='app.backtesting.strategies.'
                            if fullname.startswith(prefix) and fullname[len(prefix):]+'.py' in modules:
                                return importlib.util.spec_from_loader(fullname,self)
                            return None
                        def create_module(self,spec):return None
                        def exec_module(self,module):
                            filename=module.__name__.rsplit('.',1)[-1]+'.py'
                            module.__file__='/scratch/archived/'+filename
                            exec(compile(modules[filename],module.__file__,'exec'),module.__dict__)
                    sys.meta_path.insert(0,ArchivedLoader())
                    registry_module=types.ModuleType('app.backtesting.strategies.registry')
                    registry_module.strategy_registry=strategy_registry
                    sys.modules[registry_module.__name__]=registry_module
                    module = types.ModuleType('quarantined_strategy')
                    module.__file__ = '/scratch/quarantined_strategy.py'
                    sys.modules[module.__name__] = module
                    exec(compile(message['source'], module.__file__, 'exec'), module.__dict__)
                    classes = [v for v in module.__dict__.values() if isinstance(v, type) and v is not Strategy and issubclass(v, Strategy) and v.__module__ == module.__name__]
                    if len(classes) != 1: raise ValueError('Exactly one concrete Strategy required')
                    cls = classes[0]
                    if not isinstance(cls.spec, StrategySpec) or cls.spec.key != message['key'] or cls.on_bar is Strategy.on_bar:
                        raise ValueError('Invalid StrategySpec/key/on_bar')
                    spec = asdict(cls.spec)
                    if not cls.spec.name or not cls.spec.timeframes or any(tf not in {'1m','5m','15m','30m','1h','4h','1d','1w'} for tf in cls.spec.timeframes):
                        raise ValueError('Invalid strategy timeframes')
                    declared=set(cls.spec.defaults)|{p.key for p in (*cls.spec.parameters,*cls.spec.research_parameters)}
                    if set(message['params'])-declared:raise ValueError('Undeclared strategy parameters')
                    strategy = cls(**message['params'])
                    result = {'spec': spec}
                elif message['op'] == 'reset':
                    strategy.reset(); histories = {}; result = None
                elif message['op'] in {'bar','bar_delta'}:
                    data = message['context']
                    incoming_frames=data.pop('frames')
                    frames = {tf:pd.DataFrame(frame['rows'], columns=frame['columns']) for tf,frame in incoming_frames.items()}
                    for frame in frames.values():
                        for column in ('timestamp', 'available_at'):
                            if column in frame: frame[column] = pd.to_datetime(frame[column], utc=True)
                    if message['op']=='bar_delta':
                        for tf,frame in frames.items():
                            previous=histories.get(tf)
                            offset=incoming_frames[tf]['offset']
                            if type(offset) is not int or offset!=(len(previous) if previous is not None else 0):
                                raise ValueError('Discontinuous completed history')
                            if previous is not None and list(previous.columns)!=list(frame.columns):
                                raise ValueError('Completed history schema changed')
                            histories[tf]=frame if previous is None else pd.concat([previous,frame],ignore_index=True) if len(frame) else previous
                        # Strategy mutations cannot alter subsequent canonical context.
                        frames={tf:frame.copy(deep=True) for tf,frame in histories.items()}
                    data['decision_time'] = datetime.fromisoformat(data['decision_time'])
                    if data['position']:
                        data['position']['entry_time'] = datetime.fromisoformat(data['position']['entry_time'])
                        data['position'] = Position(**data['position'])
                    ctx = StrategyContext(**data, frames=frames, concepts=strategy.spec.concepts)
                    result = signal_to_json(strategy.on_bar(ctx))
                else: raise ValueError('Unknown operation')
            protocol.write(encode({'ok': True, 'result': result})); protocol.flush()
        except BaseException:
            # Never return arbitrary exception strings or source text.
            protocol.write(encode({'ok': False, 'error': 'STRATEGY_VALIDATION_OR_EXECUTION_FAILED'})); protocol.flush()
            return


if __name__ == '__main__': main()
