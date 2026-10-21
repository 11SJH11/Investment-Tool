"""Durable campaign control plane. No code execution or model authority lives here.

Action reservations are persisted before a service is called. Recovery preserves
the action key so the existing service can reconcile it, rather than inventing a
new experiment. A future dispatcher must register explicit supported handlers;
persisting a decision is not authorization to run arbitrary Python or consume data.
"""
from datetime import datetime, timezone
import json
from typing import Literal
from uuid import uuid4

from pydantic import Field

from .analysis import digest
from .campaign_policy import CampaignPolicy
from .dataset_planner import known_exposure, plan
from .hypotheses import Strict


class CampaignRequest(Strict):
    request_key: str = Field(min_length=1, max_length=120)
    mode: Literal['FIND_STRATEGIES', 'IMPROVE_STRATEGY', 'RESEARCH_IDEA']
    prompt: str = Field(default='', max_length=4000)
    strategy_key: str | None = Field(default=None, max_length=150)
    policy: CampaignPolicy = Field(default_factory=CampaignPolicy)


class Resources(Strict):
    simulations: int = Field(default=0, ge=0, strict=True)
    hypotheses: int = Field(default=0, ge=0, strict=True)
    children: int = Field(default=0, ge=0, strict=True)
    external_searches: int = Field(default=0, ge=0, strict=True)
    llm_calls: int = Field(default=0, ge=0, strict=True)
    llm_usd: float = Field(default=0, ge=0)
    compute_minutes: int = Field(default=0, ge=0, strict=True)


class DirectorDecision(Strict):
    request_key: str = Field(min_length=1, max_length=120)
    action: Literal['CONTINUE_DIAGNOSTICS', 'RUN_PARAMETER_EXPERIMENT',
                    'RUN_CONCEPT_DIAGNOSTIC', 'GENERATE_CHILD_STRATEGY',
                    'RUN_ROBUSTNESS', 'SIMPLIFY', 'FREEZE_CANDIDATE',
                    'REQUEST_HOLDOUT', 'VALIDATE_CANDIDATE', 'REJECT_CANDIDATE',
                    'ABANDON_STRATEGY', 'QUEUE_NEW_STRATEGY', 'ARCHIVE_PROJECT',
                    'PAUSE_CAMPAIGN', 'COMPLETE_CAMPAIGN', 'EXTERNAL_RESEARCH']
    family_id: str = Field(min_length=1, max_length=150)
    reason: str = Field(min_length=1, max_length=4000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=40)
    challenge: str = Field(min_length=1, max_length=4000)
    resources: Resources = Field(default_factory=Resources)


def utcnow():
    return datetime.now(timezone.utc)


class Campaigns:
    def __init__(self, database, *, clock=utcnow):
        self.database = database
        self.clock = clock
        with database.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS agent_campaigns(id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, document TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS agent_campaign_actions(id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, request_key TEXT NOT NULL, document TEXT NOT NULL, UNIQUE(campaign_id,request_key))')
            c.execute('CREATE TABLE IF NOT EXISTS agent_campaign_events(id INTEGER PRIMARY KEY, campaign_id TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL)')

    def _event(self, c, identifier, action, detail):
        c.execute('INSERT INTO agent_campaign_events(campaign_id,action,detail,created_at) VALUES (?,?,?,?)',
                  (identifier, action, json.dumps(detail, allow_nan=False), self.clock().isoformat()))

    @staticmethod
    def _get(c, identifier):
        row = c.execute('SELECT document FROM agent_campaigns WHERE id=?', (identifier,)).fetchone()
        if not row:
            raise ValueError('Unknown research campaign')
        return json.loads(row[0])

    @staticmethod
    def _save(c, item):
        c.execute('UPDATE agent_campaigns SET document=? WHERE id=?', (json.dumps(item, allow_nan=False), item['id']))

    def defaults(self, policy=None):
        key = 'research_campaign_policy_v1'
        with self.database.connect() as c:
            if policy is not None:
                value = CampaignPolicy.model_validate(policy).model_dump()
                c.execute('INSERT INTO app_settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                          (key, json.dumps(value)))
            row = c.execute('SELECT value FROM app_settings WHERE key=?', (key,)).fetchone()
        return CampaignPolicy.model_validate(json.loads(row[0]) if row else {}).model_dump()

    def create(self, request):
        submitted_identity = digest(request)
        # Retrying an omitted-defaults request must retain its original snapshot.
        with self.database.connect() as c:
            row = c.execute('SELECT document FROM agent_campaigns WHERE request_key=?', (request.get('request_key'),)).fetchone()
            if row:
                old = json.loads(row[0])
                if old['submitted_identity'] != submitted_identity:
                    raise ValueError('Campaign request key is immutable')
                return old
        if 'policy' not in request:
            request = {**request, 'policy': self.defaults()}
        payload = CampaignRequest.model_validate(request).model_dump()
        if payload['mode'] == 'IMPROVE_STRATEGY' and not payload['strategy_key']:
            raise ValueError('Improve mode requires a strategy key')
        if payload['mode'] == 'RESEARCH_IDEA' and not payload['prompt']:
            raise ValueError('Research idea mode requires an idea')
        if payload['strategy_key']:
            from app.backtesting.strategies import strategy_registry
            if payload['strategy_key'] not in {s.key for s in strategy_registry.specs()}:
                raise ValueError('Unknown parent strategy')
        identity = digest(payload)
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT document FROM agent_campaigns WHERE request_key=?', (payload['request_key'],)).fetchone()
            if row:
                old = json.loads(row[0])
                if old['submitted_identity'] != submitted_identity:
                    raise ValueError('Campaign request key is immutable')
                return old
            item = dict(id=str(uuid4()), identity=identity, submitted_identity=submitted_identity, request=payload, status='DRAFT',
                        created_at=self.clock().isoformat(), started_at=None, deadline=None,
                        queue=[], plans={}, reserved=Resources().model_dump(), stop_after_current=False)
            c.execute('INSERT INTO agent_campaigns VALUES (?,?,?)', (item['id'], payload['request_key'], json.dumps(item)))
            self._event(c, item['id'], 'CREATED', {'identity': identity, 'policy_hash': digest(payload['policy'])})
        return item

    def get(self, identifier):
        with self.database.connect() as c:
            return self._get(c, identifier)

    def list(self):
        with self.database.connect() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT document FROM agent_campaigns ORDER BY rowid DESC')]

    def prepare(self, identifier, entries, coverages, *, discovery=None):
        """Freeze metadata before execution. Entries are trusted registry identities."""
        from app.backtesting.strategies import strategy_registry
        from .dataset_planner import SessionCoverage
        if not entries or not coverages:
            raise ValueError('Queue and verified session coverage are required')
        keys = {s.key for s in strategy_registry.specs()}
        normalized = []
        for e in entries:
            if set(e) != {'family_id', 'strategy_key', 'reason'} or e['strategy_key'] not in keys:
                raise ValueError('Queue entries need a registered strategy, family and rationale')
            if not all(isinstance(v, str) and 0 < len(v) <= 4000 for v in e.values()):
                raise ValueError('Invalid queue entry')
            normalized.append({**e, 'state': 'QUEUED', 'source': strategy_registry.provenance(e['strategy_key'])})
        if len({e['family_id'] for e in normalized}) != len(normalized):
            raise ValueError('Duplicate family identities')
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            item = self._get(c, identifier)
            if item['status'] != 'DRAFT' and not (item['status']=='PREPARING' and
                    discovery and discovery.get('version')=='provider_cache_discovery_v1'):
                raise ValueError('Campaign plan is frozen after preparation')
            policy = item['request']['policy']
            if len(entries) > policy['budget']['families']:
                raise ValueError('Campaign family budget exceeded')
            plans = {}
            for raw in coverages:
                coverage = SessionCoverage.model_validate(raw)
                if coverage.completed_through >= self.clock().date():
                    raise ValueError('Coverage must end before the current UTC date; current sessions may be incomplete')
                if coverage.symbol not in policy['symbols'] or coverage.timeframe not in policy['timeframes']:
                    raise ValueError('Coverage outside campaign policy')
                key = coverage.symbol + ':' + coverage.timeframe
                if key in plans:
                    raise ValueError('Duplicate coverage identity')
                plans[key] = plan(coverage, policy['dataset'], exposure=known_exposure(self.database, coverage.symbol))
            if set(plans) != {s + ':' + t for s in policy['symbols'] for t in policy['timeframes']}:
                raise ValueError('Verified coverage is required for every policy symbol/timeframe')
            item.update(queue=normalized, plans=plans, status='PREPARED')
            if discovery is not None:
                item['discovery'] = discovery
            item['plan_hash'] = digest({'queue': normalized, 'plans': plans, 'policy': policy})
            self._save(c, item)
            self._event(c, identifier, 'PLAN_FROZEN', {'plan_hash': item['plan_hash']})
        return item

    def transition(self, identifier, action):
        # START is deliberately absent until the Director dispatcher is integrated.
        transitions = {'pause': ({'ACTIVE', 'STOPPING', 'PREPARING'}, 'PAUSED'),
                       'cancel': ({'DRAFT', 'PREPARING', 'PREPARED', 'ACTIVE', 'STOPPING', 'PAUSED'}, 'CANCELLED'),
                       'stop_after_current': ({'ACTIVE'}, 'STOPPING')}
        if action not in transitions:
            raise ValueError('Unsupported campaign transition')
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            item = self._get(c, identifier)
            allowed, target = transitions[action]
            if item['status'] == target:
                return item
            if item['status'] not in allowed:
                raise ValueError('Invalid campaign state transition')
            item['status'] = target
            item['stop_after_current'] = action == 'stop_after_current'
            self._save(c, item)
            self._event(c, identifier, action.upper(), {})
        return item

    def reserve(self, identifier, decision):
        """Internal dispatcher gate; no external API may bypass its state/authority."""
        decision = DirectorDecision.model_validate(decision).model_dump()
        identity = digest(decision)
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            item = self._get(c, identifier)
            prior = c.execute('SELECT document FROM agent_campaign_actions WHERE campaign_id=? AND request_key=?',
                              (identifier, decision['request_key'])).fetchone()
            if prior:
                old = json.loads(prior[0])
                if old['identity'] != identity:
                    raise ValueError('Action key is immutable')
                return old
            if item['status'] != 'ACTIVE' or not item['deadline'] or self.clock() >= datetime.fromisoformat(item['deadline']):
                raise ValueError('Campaign is inactive or its wall-clock budget is exhausted')
            policy = item['request']['policy']
            family = next((f for f in item['queue'] if f['family_id'] == decision['family_id']), None)
            if not family or family['state'] in {'ABANDONED', 'REJECTED', 'ARCHIVED'}:
                raise ValueError('Unknown or exhausted campaign family')
            if decision['action'] == 'GENERATE_CHILD_STRATEGY' and not policy['code_generation']:
                raise ValueError('Code generation is outside campaign authority')
            if decision['action'] == 'EXTERNAL_RESEARCH' and not policy['external_research']:
                raise ValueError('External research is outside campaign authority')
            if decision['action'] == 'RUN_CONCEPT_DIAGNOSTIC' and not policy['concept_research']:
                raise ValueError('Concept research is outside campaign authority')
            if decision['action'] == 'VALIDATE_CANDIDATE':
                raise ValueError('A candidate-bound holdout grant is required; campaign policy alone is not a grant')
            if decision['resources']['llm_calls'] and not policy['send_development_summaries']:
                raise ValueError('Model consent is required')
            # Estimates come from trusted action handlers, not an LLM's arithmetic.
            totals = {k: item['reserved'][k] + v for k, v in decision['resources'].items()}
            if any(value > policy['budget'][k] for k, value in totals.items()):
                raise ValueError('Campaign resource budget exhausted')
            pending = c.execute("SELECT 1 FROM agent_campaign_actions WHERE campaign_id=? AND json_extract(document,'$.status') IN ('RESERVED','RUNNING','RECONCILE')", (identifier,)).fetchone()
            if pending:
                raise ValueError('Reconcile the current action before reserving another')
            record = dict(id=str(uuid4()), campaign_id=identifier, identity=identity,
                          decision=decision, status='RESERVED', created_at=self.clock().isoformat(),
                          service_key='campaign:' + identifier + ':' + decision['request_key'], evidence=None)
            item['reserved'] = totals
            self._save(c, item)
            c.execute('INSERT INTO agent_campaign_actions VALUES (?,?,?,?)',
                      (record['id'], identifier, decision['request_key'], json.dumps(record)))
            self._event(c, identifier, 'ACTION_RESERVED', {'id': record['id'], 'decision': decision})
        return record

    def report(self, identifier):
        from .campaign_report import evidence_report
        from .campaign_progress import baseline_progress
        with self.database.connect() as c:
            item = self._get(c, identifier)
            actions = [json.loads(r[0]) for r in c.execute('SELECT document FROM agent_campaign_actions WHERE campaign_id=? ORDER BY rowid', (identifier,))]
            events = [dict(r) for r in c.execute('SELECT * FROM agent_campaign_events WHERE campaign_id=? ORDER BY id', (identifier,))]
            held = []
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_datasets'").fetchone():
                held = [json.loads(r[0]) for r in c.execute('SELECT document FROM agent_datasets')
                        if json.loads(r[0]).get('campaign_id') == identifier and json.loads(r[0])['state'] == 'INSPECTED_VALIDATION']
        execution = item.get('execution') or {}
        entries = execution.get('entries', [])
        return dict(campaign=item, actions=actions, events=events, morning_report=evidence_report(self.database,item),
                    progress=baseline_progress(self.database, item),
                    summary={'actions_reserved': len(actions),
                             'actions_completed': sum(a['status'] == 'COMPLETED' for a in actions),
                             'budget_reserved': item['reserved'],
                             'holdout_consumed_by_campaign': bool(held),
                             'execution_available': bool(execution),
                             'baseline_runs_completed': sum(bool(e.get('run_id')) for e in entries),
                             'numeric_cycles_completed': sum(e.get('completed_cycles', 0) for e in entries),
                             'structural_checks_completed':sum(e.get('structural_result',{}).get('status')=='COMPLETED' for e in entries),
                             'projects_failed_or_stopped': sum(e['state'] in {'FAILED','RESEARCH_STOPPED'} for e in entries),
                             'limitation': 'Automatic preparation, baselines, bounded numeric research and first-session Docker child checks. Full child robustness, novel idea synthesis and promotion remain unavailable.'})
