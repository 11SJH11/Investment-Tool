"""Immutable completed-minute log and provider-supplied session authority.

No weekday/holiday inference, synthetic bars, provider requests or strategy calls.
All timestamps are normalized to UTC. Calendar gaps are explicit failures.
"""
from datetime import datetime, timedelta, timezone
import json
import math
from .deployments import encoded, digest


def stamp(value):
    value = datetime.fromisoformat(value.replace('Z','+00:00')) if isinstance(value,str) else value
    if not isinstance(value,datetime) or value.tzinfo is None:
        raise ValueError('Timezone-aware timestamp required')
    return value.astimezone(timezone.utc)


def canonical(bar, observed_at):
    if set(bar)-{'timestamp','available_at','open','high','low','close','volume'}:
        raise ValueError('Unexpected completed-bar field')
    start=stamp(bar['timestamp']); available=stamp(bar['available_at'])
    if start.second or start.microsecond or available!=start+timedelta(minutes=1):
        raise ValueError('A complete, minute-aligned one-minute bar is required')
    if available>observed_at:
        raise ValueError('Incomplete/future bar rejected')
    values={k:float(bar[k]) for k in ('open','high','low','close','volume')}
    if any(not math.isfinite(v) for v in values.values()) or values['volume']<0:
        raise ValueError('Non-finite OHLCV or negative volume')
    if min(values[k] for k in ('open','high','low','close'))<=0 or not (
        values['low']<=min(values['open'],values['close'])<=max(values['open'],values['close'])<=values['high']):
        raise ValueError('Invalid OHLC range')
    return dict(timestamp=start.isoformat(),available_at=available.isoformat(),**values)


class BarLog:
    def __init__(self,database,clock=lambda:datetime.now(timezone.utc)):
        self.database=database;self.clock=clock
        with database.connect() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS forward_feeds(
                experiment_id TEXT PRIMARY KEY, identity_json TEXT NOT NULL,
                sessions_json TEXT NOT NULL, start_at TEXT NOT NULL,
                FOREIGN KEY(experiment_id) REFERENCES forward_experiments(id))''')
            c.execute('''CREATE TABLE IF NOT EXISTS forward_bars(
                experiment_id TEXT NOT NULL, timestamp TEXT NOT NULL,
                payload TEXT NOT NULL, sha256 TEXT NOT NULL, observed_at TEXT NOT NULL,
                PRIMARY KEY(experiment_id,timestamp),
                FOREIGN KEY(experiment_id) REFERENCES forward_feeds(experiment_id))''')

    def bind(self,experiment,*,provider,feed,sessions):
        if not provider or not feed or len(provider)>80 or len(feed)>80:
            raise ValueError('Explicit provider/feed identity required')
        normalized=[]
        for s in sessions:
            opening,closing=stamp(s['open']),stamp(s['close'])
            if opening>=closing or (closing-opening)>timedelta(hours=8) or any(t.second or t.microsecond for t in (opening,closing)):
                raise ValueError('Invalid provider session schedule')
            if normalized and opening<=stamp(normalized[-1]['close']):
                raise ValueError('Session schedule must be ordered and disjoint')
            normalized.append(dict(open=opening.isoformat(),close=closing.isoformat()))
        if not normalized:
            raise ValueError('Provider session schedule required; holidays are not inferred')
        identity=encoded(dict(provider=provider,feed=feed,symbol='QQQ',timeframe='1m',adjustment='raw'))
        schedule=encoded(normalized)
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT * FROM forward_feeds WHERE experiment_id=?',(experiment,)).fetchone()
            if old:
                if old['identity_json']!=identity or old['sessions_json']!=schedule:
                    raise ValueError('Forward feed and calendar are immutable')
                return dict(old)
            if not c.execute('SELECT 1 FROM forward_experiments WHERE id=?',(experiment,)).fetchone():
                raise ValueError('Unknown experiment')
            current=stamp(self.clock())
            # The first eligible live bar starts at or after binding, never in its past.
            start=current.replace(second=0,microsecond=0)
            if current>start:start+=timedelta(minutes=1)
            c.execute('INSERT INTO forward_feeds VALUES (?,?,?,?)',(experiment,identity,schedule,start.isoformat()))
            return dict(c.execute('SELECT * FROM forward_feeds WHERE experiment_id=?',(experiment,)).fetchone())

    def append(self,experiment,bars):
        observed=stamp(self.clock())
        values=[canonical(bar,observed) for bar in bars]
        if any(a['timestamp']>=b['timestamp'] for a,b in zip(values,values[1:])):
            raise ValueError('Incoming bars must be unique and chronological')
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM forward_feeds WHERE experiment_id=?',(experiment,)).fetchone()
            if not row:raise ValueError('Bind the provider feed before ingestion')
            sessions=json.loads(row['sessions_json'])
            last=c.execute('SELECT max(timestamp) FROM forward_bars WHERE experiment_id=?',(experiment,)).fetchone()[0]
            count=0
            for bar in values:
                at=bar['timestamp'];checksum=digest(bar)
                prior=c.execute('SELECT sha256 FROM forward_bars WHERE experiment_id=? AND timestamp=?',(experiment,at)).fetchone()
                if prior:
                    if prior[0]!=checksum:raise ValueError('Previously observed bar changed; reconciliation required')
                    continue
                if last and at<=last:raise ValueError('Out-of-order unseen bar rejected')
                session=next((s for s in sessions if s['open']<=at<s['close']),None)
                if not session:raise ValueError('Bar outside provider session authority')
                if last:
                    expected=stamp(last)+timedelta(minutes=1)
                    expected=next((max(expected,stamp(s['open'])) for s in sessions if stamp(s['close'])>expected),None)
                    if expected!=stamp(at):raise ValueError('Missing completed minute; ingestion halted')
                c.execute('INSERT INTO forward_bars VALUES (?,?,?,?,?)',(experiment,at,encoded(bar),checksum,observed.isoformat()))
                last=at;count+=1
            return count

    def read(self,experiment):
        with self.database.connect() as c:
            feed=c.execute('SELECT * FROM forward_feeds WHERE experiment_id=?',(experiment,)).fetchone()
            if not feed:raise ValueError('Unknown forward feed')
            values=[]
            for row in c.execute('SELECT * FROM forward_bars WHERE experiment_id=? ORDER BY timestamp',(experiment,)):
                bar=json.loads(row['payload'])
                if digest(bar)!=row['sha256'] or bar['timestamp']!=row['timestamp']:
                    raise ValueError('Completed bar integrity failed')
                values.append(bar)
            return dict(feed),values
