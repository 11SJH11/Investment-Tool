"""In-memory engine continuation; durable recovery must replay immutable bars.

Not a serialized strategy format and never deserialized from user input.
Session closes must come from an explicit exchange-calendar snapshot.
"""
from dataclasses import asdict


class IncrementalState:
    def __init__(self, session_closes):
        self.session_closes = dict(session_closes)
        self.values = {}
        self.identity = None
        self.result = None

    def bind(self, config, strategies, primary_timeframe):
        if config.force_close_time is not None:
            raise ValueError('Incremental mode requires calendar session closes, not a force-close override')
        identity = (asdict(config), {k:id(v) for k,v in strategies.items()}, primary_timeframe)
        if self.identity is not None and self.identity != identity:
            raise ValueError('Incremental engine configuration or strategy instance changed')
        self.identity = identity

    def snapshot(self):
        """Inspectable state only; cannot restore executable strategy objects."""
        s = self.values
        if not s:
            return None
        return dict(balance=s['balance'], positions={k:asdict(v) for k,v in s['positions'].items()},
                    pending_entries={k:{**v,'signal':asdict(v['signal'])} for k,v in s['pending_entries'].items()},
                    pending_exits={k:asdict(v) for k,v in s['pending_exits'].items()},
                    entries_by_day={str(k):v for k,v in s['entries_by_day'].items()},
                    last_timestamp=s['last_timestamp'].isoformat())
