"""Browser-independent campaign baseline execution through existing BacktestJobs.

This first execution phase does not claim code authoring or complete research
autonomy. Prepared/provisioned projects and explicit engine settings are required.
No worker, engine, sandbox or model execution mechanism is duplicated here.
"""
from datetime import datetime, timedelta
from threading import Event, RLock, Thread
import json
import math

from .analysis import digest
from .campaigns import Campaigns, utcnow
from .campaign_projects import provision
from .repository import ResearchRepository
from . import workflow


def permitted(database, project_id):
    """Queue progress guard, including during a pause/deadline or backend restart."""
    with database.connect() as c:
        row = c.execute('SELECT document FROM agent_projects WHERE id=?', (project_id,)).fetchone()
        project = json.loads(row[0]) if row else {}
        if not project.get('campaign_id'):
            return True
        row = c.execute('SELECT document FROM agent_campaigns WHERE id=?', (project['campaign_id'],)).fetchone()
        campaign = json.loads(row[0]) if row else {}
        if campaign.get('status') not in {'ACTIVE', 'STOPPING'} or not campaign.get('deadline'):
            return False
        execution = campaign.get('execution', {})
        current = next((e for e in execution.get('entries', []) if project_id in {e['project_id'],e.get('reference_project_id')}), None)
        allowed = {'REFERENCE','AUTHOR','SANDBOX'} if project.get('campaign_reference_for') else {'RUNNING','NUMERIC'}
        return bool(current and current['state'] in allowed and current.get('deadline') and
                    utcnow() < datetime.fromisoformat(campaign['deadline']) and
                    utcnow() < datetime.fromisoformat(current['deadline']))


class ResearchDirector:
    def __init__(self, services, *, start_thread=True, clock=utcnow):
        self.services = services
        self.database = services.database
        self.clock = clock
        self.campaigns = Campaigns(self.database, clock=clock)
        self.projects = ResearchRepository(self.database)
        self.lock = RLock()
        self.stop = Event()
        self.wake = Event()
        self.thread = None
        self.last_error = None
        if start_thread:
            self.thread = Thread(target=self._run, name='research-director', daemon=True)
            self.thread.start()

    def start_baselines(self, identifier, configurations, *, numeric_cycles=0, structural=False):
        """Internal/operator integration entry point, not the final autonomous UI."""
        from app.api.strategy_lab import BacktestRequest
        with self.lock:
            campaign = self.campaigns.get(identifier)
            if campaign.get('deadline') and self.clock() >= datetime.fromisoformat(campaign['deadline']):
                raise ValueError('Original campaign deadline expired')
            if type(numeric_cycles) is not int or not 0 <= numeric_cycles <= 10:
                raise ValueError('Numeric cycle allowance must be 0 to 10')
            if type(structural) is not bool:
                raise ValueError('Structural authorization must be boolean')
            request_hash = digest(dict(configurations=configurations, numeric_cycles=numeric_cycles, structural=structural))
            if campaign.get('execution'):
                legacy_hash=digest(dict(configurations=configurations,numeric_cycles=numeric_cycles))
                if campaign['execution']['request_hash'] != request_hash and (structural or campaign['execution']['request_hash'] != legacy_hash):
                    raise ValueError('Campaign execution configuration is immutable')
                return campaign
            links = provision(self.database, identifier)
            policy = campaign['request']['policy']
            structural_cycles=policy.get('max_structural_hypotheses_per_family',1) if structural else 0
            model_status = None
            if numeric_cycles or structural:
                if not policy['send_development_summaries']:
                    raise ValueError('Campaign policy must authorize sending development summaries')
                if numeric_cycles * len(campaign['plans']) > policy['max_parameter_hypotheses_per_family']:
                    raise ValueError('Numeric cycles exceed the family parameter-research allowance')
                loop = getattr(self.services, 'research_loop', None)
                model_status = loop.committee.model.status() if loop else {}
                if not model_status.get('configured') or not model_status.get('pricing'):
                    raise ValueError('Configured and priced research model required')
            if structural:
                if not policy['code_generation']:
                    raise ValueError('Campaign policy must authorize code generation')
                if not getattr(self.services,'research_author',None) or not getattr(self.services,'research_sandbox',None):
                    raise ValueError('Code author and Docker sandbox services are required')
                self.services.research_sandbox.docker.image()
            if set(configurations) != {p['project_id'] for p in links}:
                raise ValueError('Explicit engine configuration is required for every campaign project')
            if set(campaign['request']['policy']['directions']) != {'long', 'short'}:
                raise ValueError('Baseline-only phase cannot impose a new directional strategy rule')
            entries = []
            for link in links:
                raw = configurations[link['project_id']]
                if not isinstance(raw, dict) or set(raw) - set(BacktestRequest.model_fields):
                    raise ValueError('Unknown baseline configuration fields')
                for field in ('starting_balance', 'risk_value', 'commission_per_order', 'spread_bps', 'slippage_bps', 'max_leverage'):
                    value = raw.get(field)
                    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                        raise ValueError('Explicit finite nonnegative account, risk and cost settings are required')
                if raw.get('research_experiment'):
                    raise ValueError('Campaign baseline cannot dispatch a nested experiment')
                project = self.projects.get(link['project_id'])
                plan = campaign['plans'][link['plan_key']]
                expected = dict(strategy_key=project['strategy_key'], symbols=[plan['coverage']['symbol']],
                                start_date=plan['development']['start'], end_date=plan['development']['end'],
                                primary_timeframe=plan['coverage']['timeframe'])
                full_period=structural and policy.get('structural_evaluation','bounded_samples')=='full_period'
                if full_period:expected['warmup_start_date']=plan['warmup']['start']
                if any(k in raw and raw[k] != v for k,v in expected.items()):
                    raise ValueError('Configuration cannot move the frozen strategy, market or dataset boundaries')
                payload = BacktestRequest.model_validate({**raw, **expected, 'save_run': True,
                                                          'test_role': 'development', 'research_experiment': None}).model_dump()
                entries.append(dict(**link, state='QUEUED', payload=payload,
                                    numeric_cycles=numeric_cycles,
                                    structural=structural,
                                    structural_cycles=structural_cycles,
                                    max_variants=project['research_budget']['max_variants_per_hypothesis'],
                                    max_minutes=min(project['research_budget']['max_trial_minutes'],
                                                    (policy['budget']['compute_minutes']-campaign['reserved']['compute_minutes'])//len(links)//(1+numeric_cycles+int(structural)+2*structural_cycles))))
                if structural:
                    from .campaign_projects import reference_project
                    from .robustness import plan_windows
                    entries[-1]['robustness_windows']=plan_windows(plan)
                    entries[-1]['full_period']=full_period
                    entries[-1]['reference_project_id']=reference_project(self.database,identifier,project['id'],full_period=full_period)
                    entries[-1]['reference_payload']={**payload,'end_date':payload['end_date'] if full_period else payload['start_date']}
            if any(e['max_minutes'] < 1 for e in entries):
                raise ValueError('Campaign compute budget cannot fund these project cycles')
            with self.database.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                current = self.campaigns._get(c, identifier)
                if current['status'] != 'PREPARED' or current.get('execution'):
                    raise ValueError('Campaign changed during authorization')
                calls = (3 * numeric_cycles + 4*structural_cycles) * len(entries)
                required = dict(simulations=sum(1 + numeric_cycles*(e['max_variants']+1)+int(structural)+(4+8*len(e.get('robustness_windows',[])))*structural_cycles for e in entries),
                                hypotheses=(numeric_cycles+structural_cycles)*len(entries), children=structural_cycles*len(entries), llm_calls=calls,
                                llm_usd=calls*model_status['pricing']['call_reservation_microusd']/1000000 if calls else 0,
                                compute_minutes=sum(e['max_minutes']*(1+numeric_cycles+int(structural)+2*structural_cycles) for e in entries))
                for k,v in required.items():
                    if current['reserved'][k] + v > current['request']['policy']['budget'][k]:
                        raise ValueError('Campaign baseline budget exhausted')
                    current['reserved'][k] += v
                current.update(status='ACTIVE', started_at=current.get('started_at') or self.clock().isoformat(),
                               deadline=current.get('deadline') or (self.clock()+timedelta(minutes=current['request']['policy']['budget']['wall_minutes'])).isoformat(),
                               execution=dict(version='campaign_development_v1', request_hash=request_hash,
                                              entries=entries, model=model_status,
                                              limitation='Generated children use the frozen evaluation scope plus bounded development cost samples. Neither grants unseen validation or automatic promotion.'))
                # Cap the existing services themselves: other entry points cannot
                # spend beyond the campaign's conservative prepaid allocation.
                for e in entries:
                    project = json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?', (e['project_id'],)).fetchone()[0])
                    project['research_budget'].update(max_trial_runs=numeric_cycles*(e['max_variants']+1),
                        max_trial_minutes=e['max_minutes'], max_hypotheses=max(1,numeric_cycles),
                        max_llm_calls=3*numeric_cycles, max_llm_spend_usd=3*numeric_cycles*model_status['pricing']['call_reservation_microusd']/1000000 if numeric_cycles else 0)
                    c.execute('UPDATE agent_projects SET document=? WHERE id=?', (json.dumps(project), e['project_id']))
                if structural:
                    for e in entries:
                        project=json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?',(e['reference_project_id'],)).fetchone()[0])
                        project['research_budget'].update(max_trial_runs=(4+8*len(e['robustness_windows']))*structural_cycles,max_trial_minutes=e['max_minutes'],
                            max_llm_calls=4*structural_cycles,max_llm_spend_usd=4*structural_cycles*model_status['pricing']['call_reservation_microusd']/1000000)
                        c.execute('UPDATE agent_projects SET document=? WHERE id=?',(json.dumps(project),project['id']))
                self.campaigns._save(c, current)
                self.campaigns._event(c, identifier, 'DEVELOPMENT_AUTHORIZED', {'resources': required, 'request_hash': request_hash})
            self.wake.set()
            return current

    def control(self, identifier, action):
        with self.lock:
            current = self.campaigns.get(identifier)
            if action=='stop_after_current' and current['status']=='PREPARING':
                # Current provider call may finish; the warmup guard prevents the
                # next chunk. No thread is killed in the middle of a cache write.
                item=self.campaigns.transition(identifier,'pause')
                self._cancel_current(item)
                return item
            if action == 'resume':
                with self.database.connect() as c:
                    c.execute('BEGIN IMMEDIATE')
                    item = self.campaigns._get(c, identifier)
                    preparation = item.get('preparation') and not item.get('execution')
                    if item['status'] != 'PAUSED' or not (item.get('execution') or preparation):
                        raise ValueError('Only a paused execution can resume')
                    if self.clock() >= datetime.fromisoformat(item['deadline']):
                        raise ValueError('Original campaign deadline expired')
                    if preparation and self.clock() >= datetime.fromisoformat(item['preparation']['deadline']):
                        raise ValueError('Original history preparation deadline expired')
                    # An interrupted/cancelled queue item is reconciled, not retried.
                    item.update(status='PREPARING' if preparation else 'ACTIVE', stop_after_current=False)
                    self.campaigns._save(c, item)
                    self.campaigns._event(c, identifier, 'RESUMED', {})
            else:
                item = self.campaigns.transition(identifier, action)
                if action in {'pause', 'cancel'}:
                    self._cancel_current(item)
            self.wake.set()
            return self.campaigns.get(identifier)

    def _cancel_current(self, item):
        from .preparation import stop_jobs
        stop_jobs(self.services,item)
        for entry in item.get('execution', {}).get('entries', []):
            if entry['state']=='SANDBOX' and entry.get('sandbox_id'):
                self.services.research_sandbox.cancel(entry['reference_project_id'],entry['sandbox_id'])
            if entry['state'] == 'NUMERIC':
                loop = self.services.research_loop.get(entry['project_id'])
                if loop and loop['status'] == 'ACTIVE':
                    self.services.research_loop.pause(entry['project_id'])
            if entry['state'] in {'RUNNING','REFERENCE'}:
                pid=entry['reference_project_id'] if entry['state']=='REFERENCE' else entry['project_id']
                with self.database.connect() as c:
                    row = c.execute('SELECT id FROM backtest_jobs WHERE request_key=?', ('agent-baseline:'+pid,)).fetchone()
                if row:
                    try: self.services.backtest_jobs.cancel(row[0])
                    except ValueError: pass  # Already terminal/deleted; never remove saved evidence.

    def tick(self):
        with self.lock:
            for item in self.campaigns.list():
                if self.stop.is_set(): return
                if item.get('launch') and item['status'] in {'DRAFT','PREPARED'}:
                    try:
                        from .launch import advance
                        advance(self,item)
                    except Exception:
                        with self.database.connect() as c:
                            current=self.campaigns._get(c,item['id'])
                            current.update(status='PREPARATION_FAILED',last_error='campaign_launch_failed')
                            self.campaigns._save(c,current)
                            self.campaigns._event(c,item['id'],'LAUNCH_FAILED',{})
                    continue
                if item['status']=='PREPARING':
                    from .preparation import advance
                    advance(self.services,item['id'])
                    continue
                if item['status'] not in {'ACTIVE', 'STOPPING'} or not item.get('execution'): continue
                try: self._advance(item)
                except Exception:
                    # Fail closed on infrastructure errors, without logging provider secrets.
                    with self.database.connect() as c:
                        current = self.campaigns._get(c, item['id'])
                        if current['status'] in {'ACTIVE', 'STOPPING'}:
                            current.update(status='PAUSED', last_error='campaign_coordination_failed')
                            self.campaigns._save(c, current)
                            self.campaigns._event(c, item['id'], 'COORDINATION_FAILED', {})
                    self._cancel_current(item)

    def _advance(self, item):
        if self.clock() >= datetime.fromisoformat(item['deadline']):
            item['status'] = 'BUDGET_EXHAUSTED'
            self._save(item, 'WALL_BUDGET_EXHAUSTED')
            self._cancel_current(item)
            return
        entries = item['execution']['entries']
        current = next((e for e in entries if e['state'] in {'RUNNING', 'NUMERIC','REFERENCE','AUTHOR','SANDBOX'}), None)
        if not current:
            if item['status'] == 'STOPPING':
                item['status'] = 'PAUSED'
                self._save(item, 'STOPPED_AFTER_CURRENT')
                return
            current = next((e for e in entries if e['state'] == 'QUEUED'), None)
            if not current:
                item['status'] = 'DEVELOPMENT_COMPLETE' if any(e.get('numeric_cycles') or e.get('structural') for e in entries) else 'BASELINES_COMPLETE'
                self._save(item, item['status'])
                return
            current.update(state='RUNNING', deadline=(self.clock()+timedelta(minutes=current['max_minutes'])).isoformat())
            self._save(item, 'BASELINE_DISPATCH_RESERVED')
        project_id = current['project_id']
        if self.clock() >= datetime.fromisoformat(current['deadline']):
            self._cancel_current(item)
            current.update(state='FAILED', error='baseline_compute_deadline')
            self._save(item, 'BASELINE_FAILED')
            return
        try:
            if current['state'] in {'REFERENCE','AUTHOR','SANDBOX'}:
                from .structural import advance
                advance(self,item,current)
                return
            if current['state'] == 'NUMERIC':
                service = self.services.research_loop
                if service.committee.model.status() != item['execution']['model']:
                    raise ValueError('Model/pricing changed after campaign authorization')
                loop = service.get(project_id)
                if loop is None:
                    loop = service.start(project_id, current['numeric_cycles'], campaign_id=item['id'])
                if loop['status'] in {'COMPLETED', 'STOPPED', 'PAUSED'}:
                    current.update(state='COMPLETED' if loop['status'] == 'COMPLETED' else 'RESEARCH_STOPPED',
                                   loop_id=loop['id'], completed_cycles=len(loop['cycles']), reason=loop.get('reason'))
                    if current.get('structural'):
                        self._structural_next(item,current)
                    self._save(item, 'NUMERIC_RESEARCH_FINISHED')
                return
            project = self.projects.get(project_id)
            if project['state'] in {'CREATED', 'BASELINE_PENDING'}:
                project = workflow.start(self.services, project_id, current['payload'], campaign_dispatch=True)
            else:
                project = workflow.observe(self.services, project_id)
            if project['state'] == 'BASELINE_ANALYSIS' and project.get('baseline_run_id'):
                current.update(state='NUMERIC' if current.get('numeric_cycles') else 'COMPLETED', run_id=project['baseline_run_id'])
                if current.get('numeric_cycles'):
                    current['deadline'] = min(datetime.fromisoformat(item['deadline']),
                        self.clock()+timedelta(minutes=current['max_minutes']*current['numeric_cycles'])).isoformat()
                elif current.get('structural'):
                    self._structural_next(item,current)
                self._save(item, 'BASELINE_COMPLETED')
            elif project['state'] not in {'BASELINE_PENDING', 'BASELINE_RUNNING'}:
                current.update(state='FAILED', error='baseline_stopped_or_failed')
                self._save(item, 'BASELINE_FAILED')
        except ValueError:
            self._cancel_current(item)
            current.update(state='FAILED', error='baseline_gate_failed')
            self._save(item, 'BASELINE_FAILED')

    def _structural_next(self,item,current):
        current.update(state='REFERENCE',deadline=min(datetime.fromisoformat(item['deadline']),
            self.clock()+timedelta(minutes=current['max_minutes']*(1+2*current.get('structural_cycles',1)))).isoformat())

    def _save(self, item, event):
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            previous = self.campaigns._get(c, item['id'])
            if previous['status'] not in {'ACTIVE', 'STOPPING'}:
                raise ValueError('Campaign authorization revoked')
            self.campaigns._save(c, item)
            self.campaigns._event(c, item['id'], event, {'entries': [{k:v for k,v in e.items() if k != 'payload'} for e in item['execution']['entries']]})

    def _run(self):
        failures = 0
        while not self.stop.is_set():
            self.wake.wait(min(60, 5 * 2**failures))
            self.wake.clear()
            if self.stop.is_set(): return
            try:
                self.tick()
                failures = 0
                self.last_error = None
            except Exception:
                failures += 1
                self.last_error = 'director_storage_unavailable'
                if failures >= 3:
                    # Bounded retries; expose supervisor failure rather than
                    # repeatedly touching broken storage or leaking exception text.
                    self.last_error = 'director_stopped_after_storage_failures'
                    return

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.thread: self.thread.join(timeout=10)
        from .preparation import stop_jobs
        for item in self.campaigns.list():
            if item['status']=='PREPARING': stop_jobs(self.services,item)
