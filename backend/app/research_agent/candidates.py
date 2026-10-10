"""Immutable development candidates with descriptive, non-ranking robustness evidence."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
import json
from .analysis import digest
from .feedback import development_feedback, compact
from .repository import ResearchRepository
from .trials import Trials


def robustness(trial, index):
    cells=trial['cells'];selected=next(c for c in cells if c['index']==index)
    comparison=selected['comparison'];child=comparison['child'];parent=comparison['parent']
    parameters=selected['payload'].get('strategy_params',{})
    neighbors=[];coverage=[]
    for axis in trial['hypothesis']['axes']:
        key=axis['parameter'];values=sorted(set(axis['values']));value=parameters[key]
        lower=[v for v in values if v<value];upper=[v for v in values if v>value]
        for side,adjacent in (('lower',lower[-1] if lower else None),('upper',upper[0] if upper else None)):
            matches=[c for c in cells if c['role']=='variant' and adjacent is not None and c['payload']['strategy_params'].get(key)==adjacent and all(c['payload']['strategy_params'].get(a['parameter'])==parameters.get(a['parameter']) for a in trial['hypothesis']['axes'] if a['parameter']!=key)]
            coverage.append({'parameter':key,'side':side,'tested':bool(matches),'value':adjacent})
            for cell in matches:
                neighbors.append({'parameter':key,'side':side,'value':adjacent,'cell':cell['index'],'run_id':cell['run_id'],'summary':compact(cell['comparison']['child']['summary'])})
    periods={}
    for dimension in ('year','month','direction'):
        a=parent['breakdowns'].get(dimension,{});b=child['breakdowns'].get(dimension,{})
        periods[dimension]=[{'period':key,'parent':compact(a[key]) if key in a else None,'candidate':compact(b[key]) if key in b else None} for key in sorted(a.keys()|b.keys())]
    warnings=['Development evidence only; freezing is not validation or acceptance.',
        'Neighbors are adjacent values in the preregistered tested grid, not a continuous sensitivity estimate.',
        'No regime coverage or engine cost rerun is inferred from calendar breakdowns or arithmetic fee stress.']
    if child['summary']['n']<30:warnings.append('Low sample: fewer than 30 candidate trades (heuristic).')
    if any(not c['tested'] for c in coverage):warnings.append('Incomplete neighborhood: at least one axis side was not tested.')
    if len([p for p in periods['year'] if p['candidate'] and p['period']!='unknown'])<2:warnings.append('Candidate lacks multiple observed calendar years.')
    if comparison['removed_large_winners']['n']:warnings.append('Candidate removes baseline large winners; inspect their contribution.')
    return {'version':'development_robustness_v1','summary':compact(child['summary']),'parent_summary':compact(parent['summary']),
        'periods':periods,'neighbors':neighbors,'neighbor_coverage':coverage,'concentration':child['concentration'],
        'fee_stress':child['fee_stress'],'path':{k:deepcopy(comparison[k]) for k in ('retained','changed_retained','removed','introduced','removed_winners','removed_losers','removed_large_winners','removed_session_close_winners','retained_parent','retained_child')},
        'warnings':warnings,'verdict':'VALIDATION_REQUIRED','automatic_promotion':False}


class Candidates:
    def __init__(self,database):
        self.database=database;self.projects=ResearchRepository(database);self.trials=Trials(database)
        with database.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS agent_candidates(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,trial_id TEXT NOT NULL,cell_index INTEGER NOT NULL,document TEXT NOT NULL,UNIQUE(project_id,trial_id,cell_index))')

    def list(self,project_id):
        self.projects.get(project_id)
        with self.database.connect() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT document FROM agent_candidates WHERE project_id=? ORDER BY rowid',(project_id,))]

    def assess(self,project_id,trial_id,index):
        project=self.projects.get(project_id)
        if project['state']!='BASELINE_ANALYSIS':raise ValueError('Research project must be active')
        # Enforce the global data firewall before result JSON is read, including the baseline.
        project=self.projects.inspect_run(project_id,project['baseline_run_id'])
        development_feedback(self.database,project,trial_id=trial_id)
        trial=self.trials.get(trial_id)
        cell=next((c for c in trial['cells'] if c['index']==index and c['role']=='variant'),None)
        if not cell:raise ValueError('Select a completed variant, not the control')
        return trial,cell,robustness(trial,index)

    def freeze(self,project_id,trial_id,index,reason):
        reason=reason.strip()
        if not 1<=len(reason)<=4000:raise ValueError('Explain why this candidate merits validation')
        # Idempotent retry returns the immutable record even if source changes later.
        existing=next((r for r in self.list(project_id) if r['trial_id']==trial_id and r['cell_index']==index),None)
        if existing:
            if existing['reason']!=reason:raise ValueError('Candidate already frozen with a different rationale')
            return existing
        trial,cell,report=self.assess(project_id,trial_id,index)
        snapshot={'configuration':deepcopy(cell['payload']),'source':trial['hypothesis']['parent_source'],
            'concepts':trial['hypothesis']['parent_concepts'],'data_fingerprint':trial['hypothesis']['data_fingerprint'],
            'result_digest':cell['comparison']['child']['result_digest'],'hypothesis':deepcopy(trial['hypothesis']),
            'robustness':report}
        document={'id':str(uuid4()),'project_id':project_id,'trial_id':trial_id,'cell_index':index,'run_id':cell['run_id'],
            'parent_run_id':trial['parent_run_id'],'state':'FROZEN','created_at':datetime.now(timezone.utc).isoformat(),
            'reason':reason,'snapshot':snapshot,'snapshot_hash':digest(snapshot),'validation_granted':False}
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            previous=c.execute('SELECT document FROM agent_candidates WHERE project_id=? AND trial_id=? AND cell_index=?',(project_id,trial_id,index)).fetchone()
            if previous:
                old=json.loads(previous[0])
                if old['reason']!=reason:raise ValueError('Candidate already frozen with a different rationale')
                return old
            current=json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?',(project_id,)).fetchone()[0])
            if current['state']!='BASELINE_ANALYSIS':raise ValueError('Research project must be active')
            if c.execute("SELECT 1 FROM agent_trials WHERE project_id=? AND json_extract(document,'$.status')='ACTIVE'",(project_id,)).fetchone():raise ValueError('Finish or pause active trials before freezing a candidate')
            # Atomic with loop authorization checks: no next experiment may be registered or approved.
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_loops'").fetchone():
                row=c.execute('SELECT document FROM agent_loops WHERE project_id=?',(project_id,)).fetchone()
                if row:
                    loop=json.loads(row[0])
                    if loop['status'] in {'ACTIVE','PAUSED'}:
                        loop.update(status='STOPPED',revision=loop['revision']+1,reason='Candidate frozen; explicit validation approval required')
                        c.execute('UPDATE agent_loops SET document=? WHERE project_id=?',(json.dumps(loop),project_id))
            c.execute('INSERT INTO agent_candidates VALUES (?,?,?,?,?)',(document['id'],project_id,trial_id,index,json.dumps(document,allow_nan=False)))
            c.execute('INSERT INTO agent_events(project_id,action,detail) VALUES (?,?,?)',(project_id,'candidate_frozen',json.dumps({'candidate_id':document['id'],'snapshot_hash':document['snapshot_hash']})))
        return document
