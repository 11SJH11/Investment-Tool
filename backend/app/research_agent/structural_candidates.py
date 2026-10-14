"""Freeze verified generated development evidence; never execute or promote code."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import uuid4

from .analysis import digest, summary, compare
from .candidates import Candidates
from .quarantine import export_draft
from .research_verdict import assess
from .source_dependencies import sandbox_modules


def verify_evidence(trial, parent, policy, parent_result):
    request=trial['request']
    if not request.get('full_period') or not request.get('full_robustness_windows'):
        raise ValueError('Full-period and complete robustness evidence required')
    if trial.get('candidate_hash')!=parent['snapshot_hash']:
        raise ValueError('Generated evidence belongs to another parent')
    if digest(trial['result'])!=trial.get('result_sha256') or summary(trial['result']['trades'])!=trial['summary']:
        raise ValueError('Generated result evidence changed')
    if trial.get('provenance',{}).get('data_fingerprint')!=parent['snapshot']['data_fingerprint']:
        raise ValueError('Generated data identity changed')
    if trial['comparison']['parent']['result_digest']!=parent['snapshot']['result_digest']:
        raise ValueError('Generated comparison parent changed')
    from .sandbox_runs import core
    identity={'market_data_fingerprint':parent['snapshot']['data_fingerprint']}
    if compare({'config':identity,'result':parent_result},{'config':identity,'result':trial['result']})!=trial['comparison']:
        raise ValueError('Generated comparison changed')
    if trial['comparison']['child']['result_digest']!=digest(core(trial['result'])):
        raise ValueError('Generated comparison child changed')
    robustness=trial.get('robustness',{})
    cells=robustness.get('cells',[])
    expected=[(i+1,w['start'],w['end'],cost) for i,w in enumerate(request['windows']) for cost in (1,2)]
    actual=[(c['window'],c['start'],c['end'],c['cost_multiplier']) for c in cells]
    if not expected or actual!=expected or robustness.get('status')!='COMPLETED':
        raise ValueError('Preregistered robustness cells are incomplete')
    for cell in cells:
        if any(cell.get('provenance',{}).get(k)!=trial['provenance'].get(k)
               for k in ('source_sha256','dependency_sha256','image_id')):
            raise ValueError('Robustness implementation identity changed')
        if not cell.get('control_parity') or not cell.get('prefix_signals_checked'):
            raise ValueError('Robustness control or causality evidence missing')
        if digest(cell['result'])!=cell['result_sha256'] or digest(cell['parent_result'])!=cell['parent_result_sha256']:
            raise ValueError('Robustness results changed')
        identity={'market_data_fingerprint':cell['data_fingerprint']}
        rebuilt=compare({'config':identity,'result':cell['parent_result']},
                        {'config':identity,'result':cell['result']})
        if rebuilt!=cell['comparison'] or summary(cell['result']['trades'])!=cell['summary']:
            raise ValueError('Robustness comparison changed')
    if any(a['data_fingerprint']!=b['data_fingerprint'] for a,b in zip(cells[::2],cells[1::2])):
        raise ValueError('Robustness cost scenarios used different data')
    decision=assess(trial,policy)
    if decision['verdict']!='PROMISING_DEVELOPMENT':
        raise ValueError('Only promising verified development evidence may be frozen')
    return decision


def freeze(database, campaign_id, project_id, sandbox_id):
    candidates=Candidates(database)
    with database.connect() as c:
        row=c.execute('SELECT document FROM agent_sandbox_runs WHERE id=? AND project_id=?',(sandbox_id,project_id)).fetchone()
        if not row:raise ValueError('Unknown generated development trial')
        trial=json.loads(row[0])
        row=c.execute('SELECT document FROM agent_campaigns WHERE id=?',(campaign_id,)).fetchone()
        campaign=json.loads(row[0]) if row else {}
    policy=campaign['request']['policy']
    parent=next((p for p in candidates.list(project_id) if p['id']==trial['candidate_id']),None)
    if not parent:raise ValueError('Frozen generated parent is missing')
    candidates.verify_sandbox_parent(project_id,parent)
    from app.storage.backtest_run_repository import BacktestRunRepository
    parent_result=BacktestRunRepository(database).get(parent['run_id'])['result']
    decision=verify_evidence(trial,parent,policy,parent_result)
    exported=export_draft(database,project_id,parent['id'],trial['draft_id'])
    draft=exported['draft'];source=exported['source']
    modules=sandbox_modules(database,parent,source)
    provenance=trial['provenance']
    if (draft['source_sha256']!=trial['source_sha256'] or provenance.get('source_sha256')!=draft['source_sha256'] or
        provenance.get('dependency_sha256')!=sha256(json.dumps(modules,sort_keys=True).encode()).hexdigest()):
        raise ValueError('Tested generated source or dependencies changed')
    snapshot=dict(configuration=deepcopy(parent['snapshot']['configuration']),
        parameters=deepcopy(trial['request']['candidate_parameters']),source=source,dependencies=modules,
        registry_key=draft['request']['registry_key'],source_sha256=draft['source_sha256'],
        parent_hash=parent['snapshot_hash'],data_fingerprint=provenance['data_fingerprint'],
        sandbox_id=sandbox_id,evidence_sha256=digest(trial),policy_sha256=digest(policy),
        result_digest=trial['result_sha256'],provenance=deepcopy(provenance),decision=decision,
        robustness={'summary':trial['summary'],'warnings':['Frozen development evidence only; isolated candidate validation is still required.']})
    document=dict(id=str(uuid4()),project_id=project_id,kind='GENERATED_DEVELOPMENT',
        trial_id='sandbox:'+sandbox_id,cell_index=-1,run_id=None,parent_run_id=parent['run_id'],
        state='FROZEN_DEVELOPMENT',created_at=datetime.now(timezone.utc).isoformat(),
        reason='Full-period and preregistered cost checks passed development triage.',
        snapshot=snapshot,snapshot_hash=digest(snapshot),validation_granted=False,execution_enabled=False)
    with database.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        previous=c.execute('SELECT document FROM agent_candidates WHERE project_id=? AND trial_id=? AND cell_index=-1',
                           (project_id,document['trial_id'])).fetchone()
        if previous:
            previous=json.loads(previous[0])
            if previous['snapshot_hash']!=document['snapshot_hash']:raise ValueError('Frozen generated evidence is immutable')
            return previous
        current=json.loads(c.execute('SELECT document FROM agent_campaigns WHERE id=?',(campaign_id,)).fetchone()[0])
        entry=next((e for e in current.get('execution',{}).get('entries',[]) if e.get('reference_project_id')==project_id),{})
        from .director import permitted
        if (current['status'] not in {'ACTIVE','STOPPING'} or entry.get('state')!='SANDBOX' or
            entry.get('sandbox_id')!=sandbox_id or entry.get('draft_id')!=trial['draft_id'] or
            current['request']['policy']!=policy or not permitted(database,project_id)):
            raise ValueError('Campaign candidate-freeze authority changed')
        latest=json.loads(c.execute('SELECT document FROM agent_sandbox_runs WHERE id=?',(sandbox_id,)).fetchone()[0])
        if digest(latest)!=snapshot['evidence_sha256']:raise ValueError('Generated evidence changed during freeze')
        c.execute('INSERT INTO agent_candidates VALUES (?,?,?,?,?)',
                  (document['id'],project_id,document['trial_id'],-1,json.dumps(document)))
        c.execute('INSERT INTO agent_events(project_id,action,detail) VALUES (?,?,?)',
                  (project_id,'generated_candidate_frozen',json.dumps({'candidate_id':document['id'],'snapshot_hash':document['snapshot_hash']})))
    return document
