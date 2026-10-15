from copy import deepcopy
import json

import pytest
from tests.test_research_trials import research
from tests.test_generated_validation import generated, request as approve
from tests.test_research_decisions import request
from app.research_agent.analysis import compare, digest
from app.research_agent.decisions import Decisions
from app.research_agent.candidates import Candidates


@pytest.fixture
def passing(generated):
    runner,project,candidate=generated;db=runner.database
    candidate['snapshot']['robustness']={'warnings':['Generated simplification and additional regimes not tested.']}
    candidate['snapshot']['provenance']['source_sha256']=candidate['snapshot']['source_sha256']
    candidate['snapshot_hash']=digest(candidate['snapshot'])
    with db.connect() as c:
        c.execute('UPDATE agent_candidates SET document=? WHERE id=?',(json.dumps(candidate),candidate['id']))
        c.execute("UPDATE agent_events SET detail=? WHERE action='generated_candidate_frozen'",
            (json.dumps({'candidate_id':candidate['id'],'snapshot_hash':candidate['snapshot_hash']}),))
    grant=approve(generated)
    # Synthetic evidence exercises verification; actual Docker execution is covered
    # separately. Deliberately invalid Python source must remain inert throughout.
    result={'trades':[dict(symbol='QQQ',direction='long',entry_time=f'2027-01-{i+1:02d}T14:30:00Z',
        exit_time=f'2027-01-{i+1:02d}T14:35:00Z',r_multiple=r,net_pnl=r,exit_reason='fixture') for i,r in enumerate([2,-1]*15)],
        'metrics':{},'equity_curve':[]}
    identity={'market_data_fingerprint':'validation-fixture'}
    grant.update(status='COMPLETED',verdict='VALIDATION_PASS',control_parity=True,
        causality={'prefix_match':True,'prefix_signals_checked':10},data_fingerprint='validation-fixture',
        result=result,parent_result=deepcopy(result),result_sha256=digest(result),parent_result_sha256=digest(result),
        comparison=compare({'config':identity,'result':result},{'config':identity,'result':result}),
        provenance={**candidate['snapshot']['provenance'],'configuration_sha256':digest(grant['configuration'])})
    with db.connect() as c:c.execute('UPDATE agent_validations SET document=? WHERE id=?',(json.dumps(grant),grant['id']))
    return runner,project,candidate,grant


def test_generated_acceptance_is_immutable_research_only_and_never_imports_source(passing):
    runner,project,candidate,grant=passing;service=Decisions(runner.database)
    before=deepcopy(candidate)
    record=service.record(project['id'],candidate['id'],request('ACCEPTED_FOR_RESEARCH'))
    assert record['validation_id']==grant['id'] and record['validation_hash']==digest(grant)
    assert record['development_warnings']==candidate['snapshot']['robustness']['warnings']
    assert 'no strategy replacement' in record['scope']
    assert service.record(project['id'],candidate['id'],request('ACCEPTED_FOR_RESEARCH'))==record
    assert next(c for c in Candidates(runner.database).list(project['id']) if c['id']==candidate['id'])==before
    with pytest.raises(ValueError,match='immutable'):service.record(project['id'],candidate['id'],request())


@pytest.mark.parametrize('fault',['result','parent','comparison','config','image','source','dependency','prefix','control',
                                 'data','dataset','criteria','status','kind','project','candidate','development','freeze_audit'])
def test_changed_or_incomplete_generated_validation_cannot_be_accepted(passing,fault):
    runner,project,candidate,grant=passing;db=runner.database
    if fault=='result':grant['result']['trades'][0]['r_multiple']=100
    elif fault=='parent':grant['parent_result']['trades'].clear()
    elif fault=='comparison':grant['comparison']['retained']=99
    elif fault=='config':grant['configuration']['risk_value']=99
    elif fault=='image':grant['image_id']='other'
    elif fault=='source':grant['provenance']['source_sha256']='other'
    elif fault=='dependency':grant['provenance']['dependency_sha256']='other'
    elif fault=='prefix':grant['causality']['prefix_signals_checked']=0
    elif fault=='control':grant['control_parity']=False
    elif fault=='data':grant['data_fingerprint']='other'
    elif fault=='dataset':grant['dataset']['start']='2027-02-01'
    elif fault=='criteria':grant['criteria']['minimum_trades']=1
    elif fault=='status':grant['status']='FAILED'
    elif fault=='kind':grant['kind']='NUMERIC'
    elif fault=='project':grant['project_id']='other'
    elif fault=='candidate':grant['candidate_id']='other'
    with db.connect() as c:
        c.execute('UPDATE agent_validations SET document=? WHERE id=?',(json.dumps(grant),grant['id']))
        if fault=='development':c.execute("UPDATE agent_sandbox_runs SET document=json_set(document,'$.changed',1)")
        if fault=='freeze_audit':c.execute("DELETE FROM agent_events WHERE action='generated_candidate_frozen'")
    service=Decisions(db)
    with pytest.raises(ValueError):service.record(project['id'],candidate['id'],request('ACCEPTED_FOR_RESEARCH'))
    assert not service.list(project['id'])


def test_generated_rejection_needs_no_holdout_and_blocks_later_validation(generated):
    runner,project,candidate=generated
    candidate['snapshot']['robustness']={'warnings':['Unvalidated']};candidate['snapshot_hash']=digest(candidate['snapshot'])
    with runner.database.connect() as c:
        c.execute('UPDATE agent_candidates SET document=? WHERE id=?',(json.dumps(candidate),candidate['id']))
        c.execute("UPDATE agent_events SET detail=? WHERE action='generated_candidate_frozen'",
            (json.dumps({'candidate_id':candidate['id'],'snapshot_hash':candidate['snapshot_hash']}),))
    record=Decisions(runner.database).record(project['id'],candidate['id'],request())
    assert record['decision']=='REJECTED' and record['validation_id'] is None
    from app.research_agent.repository import ResearchRepository
    assert ResearchRepository(runner.database).get(project['id'])['datasets'][1]['state']=='LOCKED_HOLDOUT'
    with pytest.raises(ValueError,match='final research decision'):approve(generated)


def test_generated_acceptance_requires_structured_review(passing):
    runner,project,candidate,_=passing
    with pytest.raises(ValueError,match='structured'):
        Decisions(runner.database).record(project['id'],candidate['id'],{**request('ACCEPTED_FOR_RESEARCH'),'review':None})


def test_labelled_pass_is_recomputed_from_results(passing):
    runner,project,candidate,grant=passing
    for t in grant['result']['trades']:t['r_multiple']=-1;t['net_pnl']=-1
    grant['result_sha256']=digest(grant['result'])
    identity={'market_data_fingerprint':grant['data_fingerprint']}
    grant['comparison']=compare({'config':identity,'result':grant['parent_result']},{'config':identity,'result':grant['result']})
    with runner.database.connect() as c:c.execute('UPDATE agent_validations SET document=? WHERE id=?',(json.dumps(grant),grant['id']))
    with pytest.raises(ValueError,match='criteria no longer pass'):
        Decisions(runner.database).record(project['id'],candidate['id'],request('ACCEPTED_FOR_RESEARCH'))
