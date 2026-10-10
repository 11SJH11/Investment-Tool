"""Explicitly authorized development cycles. No code generation, holdouts or promotion."""
from datetime import datetime, timezone
from threading import Event, Thread
from uuid import uuid4
import json
from .analysis import digest
from .committee import Committee
from .hypotheses import HypothesisRepository
from .repository import ResearchRepository
from .trials import Trials


def require_active(connection, project_id, loop_id):
    row=connection.execute('SELECT document FROM agent_loops WHERE project_id=?',(project_id,)).fetchone()
    if not row: raise ValueError('Research loop authorization missing')
    loop=json.loads(row[0])
    if loop['id']!=loop_id or loop['status']!='ACTIVE': raise ValueError('Research loop is not active')


def experiment_identity(axes):
    # Axis/value ordering does not create a new experiment.
    return digest(sorted([(a['parameter'],sorted(set(a['values']))) for a in axes]))


class ResearchLoop:
    def __init__(self, database, jobs, model, *, start_thread=True):
        self.database=database; self.jobs=jobs; self.committee=Committee(database,model)
        self.projects=ResearchRepository(database); self.trials=Trials(database)
        self.stop=Event();self.thread=None
        with database.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS agent_loops(project_id TEXT PRIMARY KEY, document TEXT NOT NULL)')
        if start_thread:
            self.thread=Thread(target=self._run,name='research-loop',daemon=True);self.thread.start()

    def get(self, project_id):
        self.projects.get(project_id)
        with self.database.connect() as c:
            row=c.execute('SELECT document FROM agent_loops WHERE project_id=?',(project_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def permitted(self, loop):
        if self.stop.is_set():return False
        current=self.get(loop['project_id'])
        return bool(current and current['id']==loop['id'] and current['status']=='ACTIVE' and self.projects.get(loop['project_id'])['state']=='BASELINE_ANALYSIS')

    def start(self, project_id, max_cycles):
        if type(max_cycles) is not int or not 1<=max_cycles<=10:raise ValueError('Cycle limit must be 1 to 10')
        if not self.committee.model.status()['configured']:raise ValueError('Research model is not configured')
        budget=self.projects.get(project_id).get('research_budget',{})
        if not self.committee.model.status().get('pricing') or not budget.get('max_llm_spend_usd'):
            raise ValueError('Autonomous research requires configured model prices and a positive project monetary budget')
        self.committee._evidence(project_id)  # Source, data, scope and size checks before authorization.
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_candidates'").fetchone() and c.execute("SELECT 1 FROM agent_candidates WHERE project_id=? AND json_extract(document,'$.state')='FROZEN'",(project_id,)).fetchone():
                raise ValueError('Candidate frozen; explicit validation approval is required before further autonomous research')
            if c.execute('SELECT 1 FROM agent_loops WHERE project_id=?',(project_id,)).fetchone():
                raise ValueError('This project already has a loop authorization; it cannot be reset')
            if c.execute("SELECT 1 FROM agent_trials WHERE project_id=? AND json_extract(document,'$.status')='ACTIVE'",(project_id,)).fetchone():
                raise ValueError('Finish or pause the active manual trial first')
            loop={'id':str(uuid4()),'project_id':project_id,'status':'ACTIVE','phase':'REVIEW','revision':0,
                'created_at':datetime.now(timezone.utc).isoformat(),'max_cycles':max_cycles,'cycles':[],
                'scope':'Frozen baseline development parameters only; no holdouts, code generation or promotion'}
            c.execute('INSERT INTO agent_loops VALUES (?,?)',(project_id,json.dumps(loop)))
            c.execute('INSERT INTO agent_events(project_id,action,detail) VALUES (?,?,?)',(project_id,'research_loop_authorized',json.dumps(loop)))
        return loop

    def pause(self, project_id):
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT document FROM agent_loops WHERE project_id=?',(project_id,)).fetchone()
            if not row:raise ValueError('No research loop')
            loop=json.loads(row[0])
            if loop['status']!='ACTIVE':return loop
            loop.update(status='PAUSED',revision=loop['revision']+1,reason='Paused by user; no further model roles or submissions')
            c.execute('UPDATE agent_loops SET document=? WHERE project_id=?',(json.dumps(loop),project_id))
        # Approval checks the same durable authorization transactionally. Query after revoking it.
        for trial in self.trials.list(project_id):
            if trial.get('loop_id')==loop['id'] and trial['status']=='ACTIVE':
                try:self.trials.transition(trial['id'],'pause',self.jobs)
                except ValueError:pass  # Coordinator's own authorization guard also stops it.
        return loop

    def resume(self, project_id):
        if self.projects.get(project_id)['state']!='BASELINE_ANALYSIS':raise ValueError('Resume the project first')
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT document FROM agent_loops WHERE project_id=?',(project_id,)).fetchone()
            if not row:raise ValueError('No research loop')
            loop=json.loads(row[0])
            if loop['status']!='PAUSED':raise ValueError('Only a paused loop may resume')
            # Do not retry charged/interrupted model calls. The normal review gate will stop the loop.
            loop.update(status='ACTIVE',revision=loop['revision']+1,reason='Resumed within original authorization')
            c.execute('UPDATE agent_loops SET document=? WHERE project_id=?',(json.dumps(loop),project_id))
        try:
            if loop['phase']=='WAIT':
                trial=self.trials.get(loop['trial_id'])
                if trial['status']=='PAUSED':self.trials.transition(trial['id'],'resume',self.jobs)
        except ValueError:
            self.pause(project_id)
            raise
        return self.get(project_id)

    def save(self, loop):
        revision=loop['revision'];loop['revision']+=1
        with self.database.connect() as c:
            return c.execute("UPDATE agent_loops SET document=? WHERE project_id=? AND json_extract(document,'$.revision')=? AND json_extract(document,'$.status')='ACTIVE'",(json.dumps(loop),loop['project_id'],revision)).rowcount==1

    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=5)

    def _run(self):
        while not self.stop.wait(.5):
            try:self.tick()
            except Exception:continue  # No raw model/provider exceptions in logs.

    def tick(self):
        with self.database.connect() as c:
            rows=[json.loads(r[0]) for r in c.execute("SELECT document FROM agent_loops WHERE json_extract(document,'$.status')='ACTIVE'")]
        for loop in rows:
            if self.stop.is_set():return
            try:self.advance(loop)
            except Exception:
                loop.update(status='STOPPED',reason='Research gate failed. Inspect committee/trial records; no automatic retry.')
                self.save(loop)

    def advance(self, loop):
        project_id=loop['project_id']
        if not self.permitted(loop):
            loop.update(status='STOPPED',reason='Project paused or archived');self.save(loop);return
        if len(loop['cycles'])>=loop['max_cycles']:
            loop.update(status='COMPLETED',reason='Authorized development cycle limit reached; no candidate promoted');self.save(loop);return
        if loop['phase']=='REVIEW':
            key='loop:'+loop['id']+':'+str(len(loop['cycles']))
            review=self.committee.review(project_id,key,permitted=lambda:self.permitted(loop))
            if review['status']=='RUNNING':return  # Durable in-flight review; never duplicate a call after restart.
            loop['review_id']=review['id']
            if review['status']!='COMPLETED' or review['roles']['Manager']['decision']!='RECOMMEND_EXPERIMENT':
                loop.update(status='STOPPED',reason='Committee did not complete an experiment recommendation');self.save(loop);return
            # Registration is idempotent after a crash. Equivalent earlier axes stop further searching.
            proposed=experiment_identity(review['roles']['Researcher']['axes'])
            existing=HypothesisRepository(self.database).list(project_id)
            if any(experiment_identity(h['axes'])==proposed and h.get('committee_review_id')!=review['id'] for h in existing):
                loop.update(status='STOPPED',reason='Committee proposed an already registered experiment');self.save(loop);return
            hypothesis=self.committee.preregister(project_id,review['id'],loop_id=loop['id'])
            loop.update(phase='APPROVE',hypothesis_id=hypothesis['id']);self.save(loop)
        elif loop['phase']=='APPROVE':
            trial=self.trials.approve(project_id,loop['hypothesis_id'],loop_id=loop['id'])
            loop.update(phase='WAIT',trial_id=trial['id']);self.save(loop)
        elif loop['phase']=='WAIT':
            trial=self.trials.get(loop['trial_id'])
            if trial['status']=='ACTIVE':return
            if trial['status']!='COMPLETED':
                loop.update(status='STOPPED',reason='Trial stopped before completion; no next experiment');self.save(loop);return
            loop['cycles'].append({'review_id':loop['review_id'],'hypothesis_id':loop['hypothesis_id'],'trial_id':trial['id']})
            loop.update(phase='REVIEW');self.save(loop)
