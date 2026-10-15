"""Immutable shadow experiment definitions and independent durable checkpoints.

Source archives are data only. This module never imports archived/generated code,
starts workers, submits orders, or labels historical data as future observations.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from app.storage.strategy_source_archive import store, manifest_for


STRATEGIES = {
    'VWAP_BASELINE_SHADOW_V1': 'vwap_trend_confirmation_quality_research_v5',
    'VWAP_B_SHADOW_V1': 'vwap_d6_mss15_no_opp_fvg15_research_v1',
    'VWAP_C_SHADOW_V1': 'vwap_d6_score4of5_research_v1',
    'VWAP_D_SHADOW_V1': 'vwap_d6_score5of5_research_v1',
}
D6 = dict(direction='both', entry_confirmation_bars=3, exit_confirmation_bars=2,
          max_entry_vwap_distance_bps=25, min_confirmation_displacement_bps=6,
          trend_timeframe='1d', trend_ema_length=20, engine_safety_stop_pct=90)


class ShadowAccount(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    starting_balance: float = Field(gt=0, le=1_000_000_000)
    risk_value: float = Field(gt=0, le=100)
    commission_per_order: float = Field(ge=0, le=10000)
    spread_bps: float = Field(ge=0, le=1000)
    slippage_bps: float = Field(ge=0, le=1000)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return sha256(encoded(value).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


class Deployments:
    def __init__(self, database):
        self.database = database
        with database.connect() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS forward_experiments(
                id TEXT PRIMARY KEY, request_key TEXT NOT NULL UNIQUE,
                request_json TEXT NOT NULL, created_at TEXT NOT NULL)''')
            c.execute('''CREATE TABLE IF NOT EXISTS forward_deployments(
                id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL,
                name TEXT NOT NULL, definition_json TEXT NOT NULL,
                definition_sha256 TEXT NOT NULL, state_json TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 0,
                UNIQUE(experiment_id,name),
                FOREIGN KEY(experiment_id) REFERENCES forward_experiments(id))''')

    def prepare(self, request_key, account, *, registry=None):
        """Idempotently prepare all four drafts or none; no implicit activation.

        Same request after a registry refresh returns the original frozen drafts.
        A new request creates a new experiment, never updates an existing one.
        """
        if not isinstance(request_key, str) or not request_key.strip() or len(request_key)>150:
            raise ValueError('A nonempty bounded request key is required')
        account = ShadowAccount.model_validate(account).model_dump()
        request = encoded(account)
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            previous = c.execute('SELECT id,request_json FROM forward_experiments WHERE request_key=?', (request_key,)).fetchone()
            if previous:
                if previous['request_json'] != request:
                    raise ValueError('Experiment request is immutable; use a new request key')
                return self._list(c, previous['id'])
            if registry is None:
                from app.backtesting.strategies import strategy_registry
                registry = strategy_registry
            # Existing lease prevents a concurrent refresh from mixing generations.
            with registry.executing():
                sources = registry.sources()
                specs = {s.key:s for s in registry.specs()}
                definitions = []
                for name, key in STRATEGIES.items():
                    if key not in specs:
                        raise ValueError('Required frozen strategy is not registered: '+key)
                    provenance = registry.provenance(key)
                    archive = store(c, provenance, sources)
                    if archive['status'] != 'archived':
                        raise ValueError('Complete loaded source identity is required: '+key)
                    spec = specs[key]
                    params = {**spec.defaults, **{p.key:p.default for p in spec.research_parameters}}
                    if not set(D6).issubset(params):
                        raise ValueError('Strategy no longer exposes the frozen D6 contract: '+key)
                    params.update(D6)
                    definitions.append((name, dict(version='forward_shadow_v1', mode='SHADOW',
                        strategy_key=key, implementation=provenance, source_archive=archive,
                        parameters=params, symbol='QQQ', primary_timeframe='1m',
                        required_timeframes=list(spec.timeframes), data_provider=None,
                        engine={**account, 'sizing_mode':'risk_pct', 'max_leverage':1,
                            'max_open_positions':1, 'entry_windows':[['09:30','11:30']],
                            'exchange_timezone':'America/New_York', 'max_trades_per_day':3,
                            'cooldown_minutes':0, 'allow_overnight':False,
                            'trading_weekdays':[0,1,2,3,4], 'session_end':'16:00',
                            'same_bar_policy':'stop_first'})))
            experiment = str(uuid4())
            c.execute('INSERT INTO forward_experiments VALUES (?,?,?,?)', (experiment,request_key,request,now()))
            for name, definition in definitions:
                state = dict(status='DRAFT', started_at=None, stopped_at=None,
                    last_evaluated_decision_at=None, position=None, pending=None,
                    strategy_state={}, daily_state={}, trades_today=0,
                    equity=account['starting_balance'], trade_history=[],
                    execution_enabled=False, future_oos_started_at=None)
                c.execute('INSERT INTO forward_deployments VALUES (?,?,?,?,?,?,0)',
                          (str(uuid4()),experiment,name,encoded(definition),digest(definition),encoded(state)))
            return self._list(c, experiment)

    def _list(self, c, experiment):
        result = []
        for row in c.execute('SELECT * FROM forward_deployments WHERE experiment_id=? ORDER BY name', (experiment,)):
            item = dict(row)
            item['definition'] = json.loads(item.pop('definition_json'))
            item['state'] = json.loads(item.pop('state_json'))
            if digest(item['definition']) != item['definition_sha256']:
                raise ValueError('Frozen deployment definition integrity failed')
            result.append(item)
        return result

    def list(self, experiment):
        with self.database.connect() as c:
            return self._list(c, experiment)

    def verify_sources(self, deployment):
        """Validate archived bytes without importing them or substituting disk files."""
        with self.database.connect() as c:
            row = c.execute('SELECT experiment_id FROM forward_deployments WHERE id=?', (deployment,)).fetchone()
            if not row:
                raise ValueError('Unknown deployment')
            item = next(d for d in self._list(c,row[0]) if d['id']==deployment)
            archive = item['definition']['source_archive']
            row = c.execute('SELECT manifest FROM strategy_source_archives WHERE sha256=?', (archive['sha256'],)).fetchone()
            if not row:
                raise ValueError('Frozen deployment source manifest missing')
            manifest = json.loads(row[0]); sources = {}
            for name, checksum in manifest.items():
                row = c.execute('SELECT content FROM strategy_source_blobs WHERE sha256=?', (checksum,)).fetchone()
                if not row or sha256(bytes(row[0])).hexdigest()!=checksum:
                    raise ValueError('Frozen deployment source integrity failed')
                sources[name] = bytes(row[0])
            actual, fingerprint = manifest_for(sources)
            if actual!=manifest or fingerprint!=archive['sha256'] or actual.get(archive['module'])!=archive['module_sha256']:
                raise ValueError('Frozen deployment source identity changed')
            return dict(verified=True, archive_sha256=fingerprint, module_sha256=archive['module_sha256'])
