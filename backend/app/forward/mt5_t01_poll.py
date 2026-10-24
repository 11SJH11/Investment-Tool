"""One serialized read/evaluate/checkpoint cycle; no thread or trading authority."""
from datetime import datetime, timedelta, timezone
import json
from zoneinfo import ZoneInfo

from .bars import stamp
from .deployments import digest
from .mt5_t01_feed import read_minute


def poll_once(runtime, connections, identifier, profile_id, *,
              clock=lambda:datetime.now(timezone.utc), cancelled=lambda:False, commit_guard=None):
    runtime._manual_only()
    with runtime.lock, runtime.registry.executing():
        if cancelled():
            return dict(status='cancelled', execution_enabled=False)
        with runtime.database.connect() as c:
            c.execute('BEGIN')
            row = c.execute('SELECT definition,definition_sha256,revision FROM mt5_t01_diagnostics WHERE id=?', (identifier,)).fetchone()
            if row is None:
                raise ValueError('Unknown T01 diagnostic stream')
            definition, checksum, revision = json.loads(row[0]), row[1], row[2]
            if digest(definition) != checksum:
                raise ValueError('T01 definition integrity failed')
            runtime._verify(definition)
            previous = c.execute('SELECT document,sha256,sequence FROM mt5_t01_decisions WHERE deployment_id=? ORDER BY sequence DESC LIMIT 1', (identifier,)).fetchone()
        if bool(previous) != bool(revision) or (previous and previous[2] != revision):
            raise ValueError('T01 durable frontier integrity failed')
        record = json.loads(previous[0]) if previous else None
        if previous is not None and digest(record) != previous[1]:
            raise ValueError('T01 decision integrity failed')
        now = stamp(clock())
        latest = now.replace(second=0, microsecond=0)-timedelta(minutes=1)
        if record and stamp(record['bar']['timestamp']) == latest:
            return dict(status='waiting_for_completed_minute', decision_at=record['decision_at'], execution_enabled=False)
        expected = stamp(record['bar']['available_at']) if record else latest
        if expected != latest:
            raise ValueError('T01 missed minute or clock rollback; explicit recovery required')
        if not record:
            local = latest.astimezone(ZoneInfo('America/New_York'))
            if (local.hour,local.minute) != (20,0):
                raise ValueError('T01 first observation requires the 20:00 New York minute')
        observed = read_minute(connections, profile_id, definition, expected_start=expected,
                               previous_bar=record['bar'] if record else None)
        if cancelled():
            return dict(status='cancelled', execution_enabled=False)
        # The collector rechecks identity and freshness after all broker reads.
        # Runtime commit still uses its own CAS frontier for cross-process races.
        decision = runtime.step(identifier, observed['bar'], observed_at=observed['observed_at'],
            equity=observed['equity'], commit_guard=commit_guard, feed_evidence=dict(provider='mt5', profile_id=profile_id,
                volume_basis=observed['volume_basis'], timestamp_policy=observed['timestamp_policy'],
                observation_basis=observed['observation_basis']))
        return dict(status='decision_recorded', decision=decision, execution_enabled=False)
