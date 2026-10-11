"""Durable explicitly approved development-only generated-code trials."""
from copy import deepcopy
from dataclasses import fields
from datetime import datetime, timezone
import json
from hashlib import sha256
from pathlib import Path
from threading import Event, Thread, RLock
import time
from typing import Literal
from uuid import uuid4
from pydantic import Field, model_validator
from .robustness import Window, simulation_count
from app.backtesting.engine import BacktestEngine
from app.backtesting.models import BacktestConfig
from app.services.backtest import _entry_windows, _weekdays, _optional_clock, _optional_positive_int, _optional_positive_float, SESSION_ENDS
from app.services.research_runner import input_identity
from .analysis import digest, summary
from .access import scope, check
from .candidates import Candidates
from .hypotheses import Strict, Budget
from .quarantine import export_draft
from .repository import ResearchRepository
from .sandbox import Docker, Session, RemoteStrategy, SandboxError

ACK = 'Run this quarantined source in Docker on frozen development data only'
ACTIVE = {'QUEUED','RUNNING'}


class Approval(Strict):
    control_parameters: dict[str, int|float|bool|str] = Field(max_length=40)
    candidate_parameters: dict[str, int|float|bool|str] = Field(max_length=40)
    timeout_seconds: int = Field(default=120,ge=10,le=600,strict=True)
    acknowledgement: Literal['Run this quarantined source in Docker on frozen development data only']
    windows: list[Window] = Field(default_factory=list,max_length=3)

    @model_validator(mode='after')
    def ordered(self):
        if any(a.end>=b.start for a,b in zip(self.windows,self.windows[1:])):
            raise ValueError('Robustness windows must be chronological and disjoint')
        return self


def engine_config(payload,session):
    # Same generic engine configuration and parsers as BacktestService; no strategy sizing arithmetic.
    defaults=BacktestConfig()
    names={f.name for f in fields(defaults)}-{'exchange_timezone','session_end','entry_windows','trading_weekdays','force_close_time'}
    values={k:payload[k] for k in names if k in payload and payload[k] is not None}
    values.update(entry_windows=_entry_windows(payload.get('entry_windows')),trading_weekdays=_weekdays(payload.get('trading_weekdays')),
                  session_end=SESSION_ENDS[session],force_close_time=_optional_clock(payload.get('force_close_time')) if not payload.get('allow_overnight',True) else None)
    return BacktestConfig(**values)


def core(result):return {k:result[k] for k in ('trades','metrics','equity_curve')}


def first_divergence(expected,actual,path='$'):
    if type(expected)!=type(actual):return {'path':path,'reason':'type','expected':str(type(expected).__name__),'actual':str(type(actual).__name__)}
    if isinstance(expected,dict):
        if set(expected)!=set(actual):return {'path':path,'reason':'keys','missing':sorted(set(expected)-set(actual))[:10],'extra':sorted(set(actual)-set(expected))[:10]}
        for key in sorted(expected):
            found=first_divergence(expected[key],actual[key],path+'.'+key)
            if found:return found
    elif isinstance(expected,list):
        for index,(left,right) in enumerate(zip(expected,actual)):
            found=first_divergence(left,right,f'{path}[{index}]')
            if found:return found
        if len(expected)!=len(actual):return {'path':path,'reason':'length','expected':len(expected),'actual':len(actual)}
    elif expected!=actual:return {'path':path,'reason':'value','expected':str(expected)[:300],'actual':str(actual)[:300]}
    return None


class SandboxRuns:
    def __init__(self,database,backtest,*,docker=None):
        self.database=database; self.backtest=backtest
        self.docker=docker or Docker(str(database.path.resolve()))
        self.lock=RLock(); self.thread=None; self.cancel_event=Event(); self.closed=False; self.recovered=False
        with database.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS agent_sandbox_runs(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,draft_id TEXT NOT NULL UNIQUE,document TEXT NOT NULL)')

    def list(self,project_id):
        ResearchRepository(self.database).get(project_id)
        with self.database.connect() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT document FROM agent_sandbox_runs WHERE project_id=? ORDER BY rowid',(project_id,))]

    def get(self,identifier):
        with self.database.connect() as c:row=c.execute('SELECT document FROM agent_sandbox_runs WHERE id=?',(identifier,)).fetchone()
        if not row:raise ValueError('Unknown sandbox run')
        return json.loads(row[0])

    def recover(self):
        with self.lock:
            if self.recovered:return
            self.docker.cleanup()  # Fail closed if cleanup cannot be established.
            with self.database.connect() as c:
                for row in c.execute('SELECT id,document FROM agent_sandbox_runs').fetchall():
                    item=json.loads(row['document'])
                    if item['status'] in ACTIVE:
                        item.update(status='INTERRUPTED',error='RESTART_INTERRUPTED_NO_AUTOMATIC_RETRY')
                        c.execute('UPDATE agent_sandbox_runs SET document=? WHERE id=?',(json.dumps(item),row['id']))
            self.recovered=True

    def approve(self,project_id,candidate_id,draft_id,payload):
        request=Approval.model_validate(payload).model_dump(mode='json')
        with self.lock:
            if self.closed:raise ValueError('Sandbox runner is closing')
            self.recover()
            old=next((r for r in self.list(project_id) if r['draft_id']==draft_id),None)
            if old:
                if Approval.model_validate(old['request']).model_dump(mode='json')!=request:raise ValueError('Sandbox approval is immutable; create a new draft for another experiment')
                return old
            if self.thread and self.thread.is_alive():raise ValueError('One generated-code trial may run at a time')
            draft=export_draft(self.database,project_id,candidate_id,draft_id)['draft']
            candidate=next(c for c in Candidates(self.database).list(project_id) if c['id']==candidate_id)
            Candidates(self.database).verify_sandbox_parent(project_id,candidate)
            if draft['parent_hash']!=candidate['snapshot_hash']:raise ValueError('Draft parent changed')
            image=self.docker.image()
            item=dict(id=str(uuid4()),project_id=project_id,candidate_id=candidate_id,draft_id=draft_id,
                      status='QUEUED',phase='APPROVED',request=request,reserved_runs=simulation_count(request['windows']),image_id=image,
                      candidate_hash=candidate['snapshot_hash'],source_sha256=draft['source_sha256'],
                      created_at=datetime.now(timezone.utc).isoformat(),control_parity=None,causality=None)
            with self.database.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                project=json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?',(project_id,)).fetchone()[0])
                if project['state']!='BASELINE_ANALYSIS':raise ValueError('Research project must be active')
                if project.get('campaign_id'):
                    from .structural import sandbox_authorized
                    sandbox_authorized(self.database,project,candidate_id,draft_id,request)
                from .decisions import require_undecided
                require_undecided(c,candidate_id)
                from .validation import reserved
                trials=[json.loads(r[0]) for r in c.execute('SELECT document FROM agent_trials WHERE project_id=?',(project_id,))]
                if any(t['status']=='ACTIVE' for t in trials):raise ValueError('Finish active trials first')
                budget=Budget.model_validate(project.get('research_budget',{}))
                if request['timeout_seconds']>budget.max_trial_minutes*60:raise ValueError('Requested deadline exceeds project time budget')
                if sum(t['reserved_runs'] for t in trials)+reserved(c,project_id)+item['reserved_runs']>budget.max_trial_runs:
                    raise ValueError('Trial simulation budget exhausted')
                c.execute('INSERT INTO agent_sandbox_runs VALUES (?,?,?,?)',(item['id'],project_id,draft_id,json.dumps(item)))
                c.execute('INSERT INTO agent_events(project_id,action,detail) VALUES (?,?,?)',(project_id,'sandbox_approved',json.dumps({'id':item['id'],'source_sha256':item['source_sha256'],'parent_hash':item['candidate_hash'],'request_hash':digest(request)})))
            self.cancel_event=Event()
            self.thread=Thread(target=self._execute,args=(item,candidate),daemon=True,name='ledger-sandbox-trial')
            self.thread.start()
            return item

    def _save(self,item):
        with self.database.connect() as c:
            c.execute('UPDATE agent_sandbox_runs SET document=? WHERE id=?',(json.dumps(item,allow_nan=False,default=str),item['id']))

    def _guard(self,item,deadline):
        if self.cancel_event.is_set():raise SandboxError('CANCELLED')
        if time.monotonic()>=deadline:raise SandboxError('SANDBOX_TIMEOUT')
        project=ResearchRepository(self.database).get(item['project_id'])
        if project['state']!='BASELINE_ANALYSIS':raise SandboxError('PROJECT_NOT_ACTIVE')
        if project.get('campaign_id'):
            from .director import permitted
            if not permitted(self.database,item['project_id']):raise SandboxError('CAMPAIGN_NOT_ACTIVE')

    def _execute(self,item,candidate):
        deadline=time.monotonic()+item['request']['timeout_seconds']
        try:
            item.update(status='RUNNING',phase='PREPARATION');self._save(item)
            source=export_draft(self.database,item['project_id'],item['candidate_id'],item['draft_id'])['source']
            from .quarantine import list_drafts
            key=next(d['request']['registry_key'] for d in list_drafts(self.database,item['project_id'],item['candidate_id']) if d['id']==item['draft_id'])
            config=deepcopy(candidate['snapshot']['configuration'])
            # Host-owned approval is verified above; discard old queue ownership fields, never accept them from code.
            for name in list(config):
                if name.startswith('research_') or name in {'queue_job_id','market_data_fingerprint','strategy_provenance'}:config.pop(name)
            config['save_run']=False
            with scope(self.database,item['project_id']):
                inputs=self.backtest.prepare(config,progress=lambda *args:self._guard(item,deadline))
                for symbol,frames in inputs['frames_by_symbol'].items():
                    for tf,frame in frames.items():
                        from app.backtesting.context import timeframe_delta
                        if not frame.empty:check(symbol,tf,frame['timestamp'].min(),frame['timestamp'].max()+timeframe_delta(tf))
                if input_identity(inputs)!=candidate['snapshot']['data_fingerprint']:raise SandboxError('DATA_FINGERPRINT_MISMATCH')
                from .trials import check_source
                check_source(candidate['snapshot']['hypothesis'])
                if len(inputs['symbols'])!=1 or sum(len(f) for frames in inputs['frames_by_symbol'].values() for f in frames.values())>10000:
                    raise SandboxError('SANDBOX_DATA_LIMIT_SINGLE_SYMBOL_10000_BARS')
                parent=self.backtest.run(config,prepared=inputs,progress=lambda *args:self._guard(item,deadline))
            if digest(core(parent))!=candidate['snapshot']['result_digest']:raise SandboxError('PARENT_CONTROL_MISMATCH')
            engine=engine_config(config,inputs['session']); symbol=inputs['symbols'][0]
            def simulate(parameters,phase,prefix=False,*,prepared=None,payload=None):
                self._guard(item,deadline);item['phase']=phase;self._save(item)
                started=time.monotonic()
                session=Session(self.docker,item['image_id'],seconds=max(.1,deadline-time.monotonic()),cancel=self.cancel_event)
                try:
                    strategy=RemoteStrategy(session,source,key,parameters)
                    data=prepared or inputs
                    selected_engine=engine_config(payload,data['session']) if payload is not None else engine
                    frames=data['frames_by_symbol']
                    if prefix:
                        frames=deepcopy(frames)
                        primary=frames[symbol][data['primary']]
                        frames[symbol][data['primary']]=primary.iloc[:max(1,len(primary)//2)].copy()
                    result=BacktestEngine(selected_engine).run(symbol_frames=frames,strategies={symbol:strategy},primary_timeframe=data['primary'],progress=lambda *a:self._guard(item,deadline))
                    return result,strategy.trace,session.provenance
                finally:
                    item.setdefault('resource_usage',[]).append({'phase':phase,'wall_seconds':round(time.monotonic()-started,4),'docker_terminal_sample':session.usage(),'sample_is_peak':False})
                    session.close()
            control,_,_=simulate(item['request']['control_parameters'],'CONTROL_PARITY')
            item['control_parity']=core(control)==core(parent)
            if not item['control_parity']:
                item['first_divergence']=first_divergence(core(parent),core(control))
                raise SandboxError('GENERATED_CONTROL_MISMATCH')
            result,trace,provenance=simulate(item['request']['candidate_parameters'],'CANDIDATE')
            _,prefix_trace,_=simulate(item['request']['candidate_parameters'],'CAUSALITY_PREFIX')
            if not prefix_trace or trace[:len(prefix_trace)]!=prefix_trace:raise SandboxError('CAUSALITY_OR_DETERMINISM_MISMATCH')
            self._guard(item,deadline)
            from app.storage.reproducibility import environment_snapshot
            app_root=Path(__file__).resolve().parents[1]
            host_files=('backtesting/engine.py','backtesting/models.py','backtesting/context.py','data/futures.py','research_agent/sandbox.py','research_agent/sandbox_runs.py','research_agent/sandbox_wire.py','research_agent/robustness.py')
            from .analysis import compare
            comparison=compare({'config':{**config,'market_data_fingerprint':input_identity(inputs)},'result':parent},
                               {'config':{**config,'market_data_fingerprint':input_identity(inputs)},'result':result})
            item.update(causality={'completed_bars_only':True,'prefix_signals_checked':len(prefix_trace),'prefix_match':True,
                'limitation':'Finite replay check, not proof against arbitrary malicious or nondeterministic code.'},
                provenance={**provenance,'configuration_sha256':digest(config),'data_fingerprint':input_identity(inputs),
                            'parent_hash':candidate['snapshot_hash'],'signal_trace_sha256':digest(trace),
                            'host_environment':environment_snapshot(),'host_implementation':{p:sha256((app_root/p).read_bytes()).hexdigest() for p in host_files}},
                result=result,summary=summary(result['trades']),comparison=comparison,
                result_sha256=digest(result))
            if item['request'].get('windows'):
                from .robustness import execute
                def prepare_window(payload):
                    from datetime import date, time as day_time, timedelta
                    from zoneinfo import ZoneInfo
                    zone=ZoneInfo('America/New_York')
                    begin=datetime.combine(date.fromisoformat(payload['start_date']),day_time.min,zone)
                    end=datetime.combine(date.fromisoformat(payload['end_date'])+timedelta(days=1),day_time.min,zone)
                    self._guard(item,deadline)
                    with scope(self.database,item['project_id']):
                        check(symbol,inputs['primary'],begin,end)
                        check_source(candidate['snapshot']['hypothesis'])
                        data=self.backtest.prepare(payload,progress=lambda *a:self._guard(item,deadline))
                        if data['symbols']!=[symbol] or sum(len(f) for fs in data['frames_by_symbol'].values() for f in fs.values())>10000:
                            raise SandboxError('SANDBOX_DATA_LIMIT_SINGLE_SYMBOL_10000_BARS')
                        for frames in data['frames_by_symbol'].values():
                            for tf,frame in frames.items():
                                if not frame.empty:
                                    check(symbol,tf,frame['timestamp'].min(),frame['timestamp'].max()+timeframe_delta(tf))
                                    if (tf==data['primary'] and frame['timestamp'].min()<begin) or frame['timestamp'].max()>=end:
                                        raise SandboxError('ROBUSTNESS_DATA_WINDOW_MISMATCH')
                        if data.get('source_namespaces')!=inputs.get('source_namespaces'):
                            raise SandboxError('ROBUSTNESS_PROVIDER_CHANGED')
                        parent_result=self.backtest.run(payload,prepared=data,progress=lambda *a:self._guard(item,deadline))
                    return data,parent_result,input_identity(data)
                def simulate_window(payload,data,child,phase,prefix):
                    params=item['request']['candidate_parameters' if child else 'control_parameters']
                    return simulate(params,phase,prefix,prepared=data,payload=payload)
                def save_windows(cells):
                    item['robustness']={'status':'RUNNING','cells':cells};self._save(item)
                item['robustness']=execute(item['request']['windows'],config,prepare_window,simulate_window,save_windows)
                item['robustness']['status']='COMPLETED'
            self._guard(item,deadline)
            item.update(status='COMPLETED',phase='DEVELOPMENT_REVIEW_REQUIRED')
        except BaseException as exc:
            code=str(exc) if isinstance(exc,SandboxError) else 'SANDBOX_VALIDATION_OR_EXECUTION_FAILED'
            item.update(status='CANCELLED' if self.cancel_event.is_set() else 'FAILED',error=code)
            if item.get('robustness'):
                item['robustness']['status']=item['status']
                for cell in item['robustness']['cells']:
                    if cell['status']!='COMPLETED':cell.update(status=item['status'],error=code)
        finally:
            try:self.docker.cleanup()
            except SandboxError:item.update(status='FAILED',error='SANDBOX_CLEANUP_FAILED')
            item['finished_at']=datetime.now(timezone.utc).isoformat();self._save(item)

    def cancel(self,project_id,identifier):
        with self.lock:
            item=self.get(identifier)
            if item['project_id']!=project_id:raise ValueError('Unknown sandbox run')
            if item['status'] in ACTIVE:self.cancel_event.set()
            return item

    def close(self):
        with self.lock:self.closed=True;self.cancel_event.set()
        if self.thread:self.thread.join(timeout=20)
        if self.recovered:self.docker.cleanup()
        self.docker.close()
