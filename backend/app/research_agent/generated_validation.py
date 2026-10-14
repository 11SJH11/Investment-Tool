"""Explicit holdout validation of frozen source through the existing Docker runner.

No generated module is imported here and no generated job enters the host queue.
The ordinary validation store/access firewall owns dataset exposure.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from threading import Event, Thread
import time
from uuid import uuid4

from .analysis import digest, compare
from .candidates import Candidates
from .hypotheses import Budget
from .repository import ResearchRepository
from .validation import Criteria, Validations, reserved, verdict
from .sandbox import SandboxError, Session, RemoteStrategy

KIND = 'GENERATED_ISOLATED'


def verified_candidate(database, project_id, candidate_id):
    candidate=next((c for c in Candidates(database).list(project_id) if c['id']==candidate_id),None)
    if not candidate or candidate.get('kind')!='GENERATED_DEVELOPMENT' or candidate['state']!='FROZEN_DEVELOPMENT':
        raise ValueError('Frozen generated development candidate required')
    snapshot=candidate['snapshot']
    if digest(snapshot)!=candidate['snapshot_hash']:
        raise ValueError('Frozen candidate snapshot changed')
    with database.connect() as c:
        events=[json.loads(r[0]) for r in c.execute("SELECT detail FROM agent_events WHERE project_id=? AND action='generated_candidate_frozen'",(project_id,))]
        row=c.execute('SELECT document FROM agent_sandbox_runs WHERE id=? AND project_id=?',(snapshot['sandbox_id'],project_id)).fetchone()
    if not any(e.get('candidate_id')==candidate_id and e.get('snapshot_hash')==candidate['snapshot_hash'] for e in events):
        raise ValueError('Frozen candidate audit identity changed')
    trial=json.loads(row[0]) if row else None
    if not trial or digest(trial)!=snapshot['evidence_sha256']:
        raise ValueError('Frozen development evidence changed')
    if (sha256(snapshot['source'].encode()).hexdigest()!=snapshot['source_sha256'] or
        sha256(json.dumps(snapshot['dependencies'],sort_keys=True).encode()).hexdigest()!=snapshot['provenance']['dependency_sha256']):
        raise ValueError('Frozen source bundle changed')
    parent=next((c for c in Candidates(database).list(project_id) if c['id']==trial['candidate_id']),None)
    if not parent or parent['snapshot_hash']!=snapshot['parent_hash']:
        raise ValueError('Frozen parent changed')
    Candidates(database).verify_sandbox_parent(project_id,parent)
    return candidate,parent,trial


def approve(runner, project_id, candidate_id, dataset_id, criteria):
    criteria=Criteria.model_validate(criteria).model_dump()
    store=Validations(runner.database)
    with runner.lock:
        if runner.closed:raise ValueError('Sandbox runner is closing')
        runner.recover()
        old=next((v for v in store.list(project_id) if v['candidate_id']==candidate_id),None)
        if old:
            if old.get('kind')!=KIND or old['dataset_id']!=dataset_id or old['criteria']!=criteria:
                raise ValueError('Validation grant is immutable')
            return old
        if runner.thread and runner.thread.is_alive():raise ValueError('One generated-code trial may run at a time')
        candidate,parent,trial=verified_candidate(runner.database,project_id,candidate_id)
        image=runner.docker.image()
        if image!=candidate['snapshot']['provenance']['image_id']:
            raise ValueError('Validation requires the exact development sandbox image')
        project=ResearchRepository(runner.database).get(project_id)
        dataset=next((d for d in project['datasets'] if d['id']==dataset_id),None)
        config=deepcopy(candidate['snapshot']['configuration'])
        if not dataset or dataset['state'] not in {'LOCKED_HOLDOUT','FUTURE_OOS'}:
            raise ValueError('Select an untouched dataset belonging to this project')
        if dataset['timeframe']!=config['primary_timeframe'] or set(dataset['symbols'])!=set(config['symbols']):
            raise ValueError('Validation symbol/timeframe must match the frozen candidate')
        for name in list(config):
            if name.startswith('research_') or name in {'queue_job_id','market_data_fingerprint','strategy_provenance','workspace'}:config.pop(name)
        config.update(start_date=dataset['start'],end_date=dataset['end'],save_run=False,test_role='validation')
        budget=Budget.model_validate(project.get('research_budget',{}))
        seconds=min(21600,budget.max_trial_minutes*60)
        document=dict(id=str(uuid4()),kind=KIND,project_id=project_id,candidate_id=candidate_id,
            candidate_hash=candidate['snapshot_hash'],dataset_id=dataset_id,dataset=deepcopy(dataset),criteria=criteria,
            configuration=config,status='ACTIVE',phase='APPROVED',revision=0,reserved_runs=4,
            created_at=datetime.now(timezone.utc).isoformat(),deadline=time.time()+seconds,
            image_id=image,verdict='PENDING',automatic_promotion=False,cells=[])
        with runner.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT 1 FROM agent_validations WHERE candidate_id=?',(candidate_id,)).fetchone():
                raise ValueError('Validation already approved; refresh')
            current=json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?',(project_id,)).fetchone()[0])
            if current['state']!='BASELINE_ANALYSIS' or current.get('research_budget',{})!=project.get('research_budget',{}):
                raise ValueError('Project state or budget changed')
            from .decisions import require_undecided
            require_undecided(c,candidate_id)
            current_candidate=json.loads(c.execute('SELECT document FROM agent_candidates WHERE id=?',(candidate_id,)).fetchone()[0])
            if current_candidate!=candidate:raise ValueError('Frozen candidate changed during approval')
            d=json.loads(c.execute('SELECT document FROM agent_datasets WHERE id=?',(dataset_id,)).fetchone()[0])
            if d!=dataset:raise ValueError('Dataset access changed; refresh before approving')
            trials=[json.loads(r[0]) for r in c.execute('SELECT document FROM agent_trials WHERE project_id=?',(project_id,))]
            if any(t['status']=='ACTIVE' for t in trials):raise ValueError('Finish or pause development trials first')
            if project.get('campaign_id'):
                row=c.execute('SELECT document FROM agent_campaigns WHERE id=?',(project['campaign_id'],)).fetchone()
                campaign=json.loads(row[0])
                if campaign['status']!='DEVELOPMENT_COMPLETE':raise ValueError('Finish campaign development before explicit validation')
                if not campaign.get('deadline') or datetime.now(timezone.utc)>=datetime.fromisoformat(campaign['deadline']):
                    raise ValueError('Campaign wall-clock budget exhausted')
                totals=deepcopy(campaign['reserved']);totals['simulations']+=4;totals['compute_minutes']+=seconds/60
                if any(v>campaign['request']['policy']['budget'][k] for k,v in totals.items()):
                    raise ValueError('Campaign resource budget exhausted')
                campaign['reserved']=totals
                document['deadline']=min(document['deadline'],datetime.fromisoformat(campaign['deadline']).timestamp())
                document['campaign_id']=campaign['id']
                c.execute('UPDATE agent_campaigns SET document=? WHERE id=?',(json.dumps(campaign),campaign['id']))
                # Campaign reference projects have only their development allocation.
                # This explicit grant allocates four additional simulations from the
                # remaining campaign budget, atomically with dataset exposure.
                budget=Budget.model_validate({**budget.model_dump(),'max_trial_runs':budget.max_trial_runs+4})
                current['research_budget']=budget.model_dump()
                c.execute('UPDATE agent_projects SET document=? WHERE id=?',(json.dumps(current),project_id))
            if sum(t['reserved_runs'] for t in trials)+reserved(c,project_id)+4>budget.max_trial_runs:
                raise ValueError('Simulation budget exhausted')
            d['state']='INSPECTED_VALIDATION'
            c.execute('UPDATE agent_datasets SET document=? WHERE id=?',(json.dumps(d),dataset_id))
            c.execute('INSERT INTO agent_validations VALUES (?,?,?,?)',(document['id'],project_id,candidate_id,json.dumps(document)))
            c.execute('INSERT INTO agent_events(project_id,dataset_id,action,detail) VALUES (?,?,?,?)',
                (project_id,dataset_id,'candidate_validation_approved',json.dumps({'validation_id':document['id'],'candidate_hash':candidate['snapshot_hash'],'criteria':criteria,'kind':KIND})))
        runner.cancel_event=Event()
        runner.thread=Thread(target=execute,args=(runner,deepcopy(document)),daemon=True,name='ledger-generated-validation')
        try:runner.thread.start()
        except Exception:
            document.update(status='FAILED',error='ISOLATED_VALIDATION_DISPATCH_FAILED_NO_AUTOMATIC_RETRY',
                            finished_at=datetime.now(timezone.utc).isoformat())
            store.save(document)
        return document


def execute(runner, item):
    from .access import scope, check
    from .sandbox_runs import engine_config, check_input_limits, core, first_divergence
    from .trials import check_source
    from app.services.research_runner import input_identity
    from app.backtesting.context import timeframe_delta
    from app.backtesting.engine import BacktestEngine
    store=Validations(runner.database)
    deadline=time.monotonic()+max(0,item['deadline']-time.time())

    def save():
        if not store.save(item):raise SandboxError('VALIDATION_AUTHORITY_CHANGED')

    def guard(*args):
        if runner.cancel_event.is_set():raise SandboxError('CANCELLED')
        if time.monotonic()>=deadline:raise SandboxError('SANDBOX_TIMEOUT')
        from .validation import active
        if not active(runner.database,item['id']):raise SandboxError('VALIDATION_NOT_ACTIVE')
        if item.get('campaign_id'):
            with runner.database.connect() as c:
                campaign=json.loads(c.execute('SELECT document FROM agent_campaigns WHERE id=?',(item['campaign_id'],)).fetchone()[0])
            if campaign['status']!='DEVELOPMENT_COMPLETE':raise SandboxError('CAMPAIGN_VALIDATION_STOPPED')

    try:
        candidate,parent,trial=verified_candidate(runner.database,item['project_id'],item['candidate_id'])
        if candidate['snapshot_hash']!=item['candidate_hash']:raise SandboxError('CANDIDATE_CHANGED')
        snapshot=candidate['snapshot'];config=item['configuration']
        guard();item['phase']='PREPARATION';save()
        with scope(runner.database,item['project_id'],item['id']):
            check_source(parent['snapshot']['hypothesis'])
            inputs=runner.backtest.prepare(config,progress=guard)
            check_input_limits(inputs,full_period=True)
            from datetime import date, time as day_time, timedelta
            from zoneinfo import ZoneInfo
            zone=ZoneInfo('America/New_York')
            begin=datetime.combine(date.fromisoformat(config['start_date']),day_time.min,zone)
            end=datetime.combine(date.fromisoformat(config['end_date'])+timedelta(days=1),day_time.min,zone)
            warmup=datetime.combine(date.fromisoformat(config.get('warmup_start_date') or config['start_date']),day_time.min,zone)
            if (inputs['symbols']!=config['symbols'] or inputs['primary']!=config['primary_timeframe'] or
                not begin<=inputs['start']<inputs['end']<=end):
                raise SandboxError('VALIDATION_DATA_WINDOW_MISMATCH')
            for symbol,frames in inputs['frames_by_symbol'].items():
                for tf,frame in frames.items():
                    if not frame.empty:
                        check(symbol,tf,frame['timestamp'].min(),frame['timestamp'].max()+timeframe_delta(tf))
                        if frame['timestamp'].max()>=end or (tf==inputs['primary'] and frame['timestamp'].min()<warmup):
                            raise SandboxError('VALIDATION_DATA_WINDOW_MISMATCH')
            # Prepare/run only the trusted frozen parent on the host.
            parent_result=runner.backtest.run(config,prepared=inputs,progress=guard)
        identity=input_identity(inputs);symbol=inputs['symbols'][0]
        engine=engine_config(config,inputs['session'])

        def simulate(parameters,phase,prefix=False):
            guard();item['phase']=phase;save()
            session=Session(runner.docker,item['image_id'],seconds=max(.1,deadline-time.monotonic()),cancel=runner.cancel_event)
            try:
                strategy=RemoteStrategy(session,snapshot['source'],snapshot['registry_key'],parameters,modules=snapshot['dependencies'])
                frames=inputs['frames_by_symbol']
                if prefix:
                    frames=deepcopy(frames);primary=frames[symbol][inputs['primary']]
                    warmup=int((primary['timestamp']<inputs['start']).sum()) if config.get('warmup_start_date') else 0
                    frames[symbol][inputs['primary']]=primary.iloc[:warmup+max(1,(len(primary)-warmup)//2)].copy()
                result=BacktestEngine(engine).run(symbol_frames=frames,strategies={symbol:strategy},primary_timeframe=inputs['primary'],progress=guard,
                    evaluation_start=inputs['start'] if config.get('warmup_start_date') else None)
                return result,strategy.trace,session.provenance
            finally:session.close()

        control,_,_=simulate(trial['request']['control_parameters'],'CONTROL_PARITY')
        if core(control)!=core(parent_result):
            item['first_divergence']=first_divergence(core(parent_result),core(control))
            raise SandboxError('GENERATED_CONTROL_MISMATCH')
        child,trace,provenance=simulate(snapshot['parameters'],'CANDIDATE')
        _,prefix,_=simulate(snapshot['parameters'],'CAUSALITY_PREFIX',True)
        if not prefix or trace[:len(prefix)]!=prefix:raise SandboxError('CAUSALITY_OR_DETERMINISM_MISMATCH')
        guard()
        comparison=compare({'config':{**config,'market_data_fingerprint':identity},'result':parent_result},
                           {'config':{**config,'market_data_fingerprint':identity},'result':child})
        from pathlib import Path
        from app.storage.reproducibility import environment_snapshot
        app_root=Path(__file__).resolve().parents[1]
        host_files=('backtesting/engine.py','backtesting/models.py','backtesting/context.py',
                    'research_agent/generated_validation.py','research_agent/sandbox_runs.py','research_agent/sandbox.py','research_agent/sandbox_wire.py')
        item.update(status='COMPLETED',phase='VALIDATION_REVIEW_REQUIRED',control_parity=True,
            causality={'prefix_match':True,'prefix_signals_checked':len(prefix),'limitation':'Finite prefix check, not a proof.'},
            data_fingerprint=identity,provenance={**provenance,'configuration_sha256':digest(config),'signal_trace_sha256':digest(trace),
                'host_environment':environment_snapshot(),'host_implementation':{p:sha256((app_root/p).read_bytes()).hexdigest() for p in host_files}},
            result=child,result_sha256=digest(child),parent_result=parent_result,parent_result_sha256=digest(parent_result),
            comparison=comparison,verdict=verdict(comparison['child']['summary'],item['criteria']))
    except BaseException as exc:
        item.update(status='CANCELLED' if runner.cancel_event.is_set() else 'FAILED',
            error=str(exc) if isinstance(exc,SandboxError) else 'ISOLATED_VALIDATION_FAILED_NO_AUTOMATIC_RETRY')
    finally:
        try:runner.docker.cleanup()
        except SandboxError:item.update(status='FAILED',error='SANDBOX_CLEANUP_FAILED')
        item['finished_at']=datetime.now(timezone.utc).isoformat()
        store.save(item)
