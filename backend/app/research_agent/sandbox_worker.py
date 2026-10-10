"""Container-only entry point. Never import this module in the Ledger server."""
import os
import sys


def main():
    import contextlib
    from dataclasses import asdict
    from datetime import datetime
    import types
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
    for raw in iter(lambda: incoming.readline(MAX_MESSAGE+1), b''):
        try:
            message = decode(raw, MAX_MESSAGE)
            with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                if message['op'] == 'init':
                    if strategy is not None: raise ValueError('Already initialized')
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
                    strategy.reset(); result = None
                elif message['op'] == 'bar':
                    data = message['context']
                    frames = {tf:pd.DataFrame(frame['rows'], columns=frame['columns']) for tf,frame in data.pop('frames').items()}
                    for frame in frames.values():
                        for column in ('timestamp', 'available_at'):
                            if column in frame: frame[column] = pd.to_datetime(frame[column], utc=True)
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
