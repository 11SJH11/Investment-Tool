"""Metadata-only chronological planning; never inspect performance to choose dates.

The caller supplies actual completed session dates and coverage provenance. This
module neither downloads bars nor infers complete history from cache min/max dates.
Plans are inert until the existing dataset registry accepts them transactionally.
"""
from datetime import date
import json

from pydantic import Field, model_validator

from .analysis import digest
from .campaign_policy import DatasetPolicy
from .hypotheses import Strict


class SessionCoverage(Strict):
    symbol: str = Field(min_length=1, max_length=80)
    timeframe: str = Field(min_length=1, max_length=10)
    provider_namespace: str = Field(min_length=1, max_length=200)
    source_fingerprint: str = Field(min_length=1, max_length=200)
    completed_through: date
    sessions: list[date] = Field(min_length=1, max_length=50000)

    @model_validator(mode='after')
    def chronological(self):
        from app.data.instruments import normalize_symbol
        self.symbol = normalize_symbol(self.symbol)
        if not self.symbol:
            raise ValueError('A symbol is required')
        if self.sessions != sorted(set(self.sessions)):
            raise ValueError('Coverage sessions must be unique and chronological')
        if self.sessions[-1] > self.completed_through:
            raise ValueError('Incomplete/future sessions cannot be allocated')
        return self


def known_exposure(database, symbol):
    """Only metadata is read; a saved run is exposure regardless of its performance."""
    from .access import family
    target = family(symbol)
    records = []
    with database.connect() as c:
        for row in c.execute('SELECT id,symbols,start_date,end_date FROM backtest_runs'):
            if target in {family(s) for s in json.loads(row['symbols'])}:
                records.append(dict(start=row['start_date'], end=row['end_date'], kind='SAVED_RUN', reference=str(row['id'])))
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_datasets'").fetchone():
            for row in c.execute('SELECT document FROM agent_datasets'):
                d = json.loads(row[0])
                if target in {family(s) for s in d['symbols']}:
                    records.append(dict(start=d['start'], end=d['end'], kind=d['state'], reference=d['id']))
    return records


def plan(coverage, policy=None, *, exposure=()):
    coverage = SessionCoverage.model_validate(coverage)
    policy = DatasetPolicy.model_validate(policy or {})
    sessions = coverage.sessions
    available = len(sessions) - policy.warmup_sessions
    if available < policy.min_development_sessions + policy.min_holdout_sessions:
        raise ValueError('Insufficient completed history for warmup, development and holdout')
    development_n = max(policy.min_development_sessions, available * policy.development_percent // 100)
    development_n = min(development_n, available - policy.min_holdout_sessions)
    start = policy.warmup_sessions
    boundary = start + development_n

    def window(first, last):
        return dict(start=sessions[first].isoformat(), end=sessions[last].isoformat(), sessions=last-first+1)

    warmup = window(0, start-1)
    development = window(start, boundary-1)
    holdout = window(boundary, len(sessions)-1)
    internal = [window(start + development_n*i//policy.internal_windows,
                       start + development_n*(i+1)//policy.internal_windows-1)
                for i in range(policy.internal_windows)]
    warnings = []
    conflicts = []
    for e in exposure:
        first, last = date.fromisoformat(e['start']), date.fromisoformat(e['end'])
        if first > last:
            raise ValueError('Invalid exposure interval')
        protected = e['kind'] in {'LOCKED_HOLDOUT', 'FUTURE_OOS'}
        if protected and first <= sessions[boundary-1] and sessions[0] <= last:
            raise ValueError('Planned development or warmup overlaps protected history')
        if first <= sessions[-1] and sessions[boundary] <= last:
            conflicts.append(dict(e))
    # Never move a boundary to search for a more convenient unseen interval.
    state = 'UNAVAILABLE' if conflicts else 'PROPOSED_UNSEEN'
    if conflicts:
        warnings.append('Fixed holdout overlaps registered or inspected history; it cannot be called unseen. No dates were moved.')
    warnings.append('Coverage comes from the named session manifest; provider completeness and unknown manual inspections are not inferred.')
    result = dict(version='chronological_session_plan_v1', policy=policy.model_dump(),
                  coverage=coverage.model_dump(mode='json', exclude={'sessions'}),
                  session_manifest_hash=digest([d.isoformat() for d in sessions]),
                  warmup=warmup, development=development, internal_development_windows=internal,
                  holdout={**holdout, 'state': state, 'conflicts': conflicts},
                  future_oos=None, warnings=warnings,
                  dataset_proposal=[dict(start=warmup['start'], end=development['end'],
                                         symbols=[coverage.symbol], timeframe=coverage.timeframe, state='DEVELOPMENT')])
    if not conflicts:
        result['dataset_proposal'].append(dict(start=holdout['start'], end=holdout['end'],
                                              symbols=[coverage.symbol], timeframe=coverage.timeframe, state='LOCKED_HOLDOUT'))
    result['plan_hash'] = digest(result)
    return result
