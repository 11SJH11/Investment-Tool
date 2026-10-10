from copy import deepcopy
from types import SimpleNamespace
import json
import pytest
from tests.test_research_trials import research
from tests.test_research_feedback import completed
from app.research_agent.candidates import Candidates, robustness
from app.research_agent.analysis import digest
from app.research_agent.loop import ResearchLoop
from tests.test_research_loop import priced_model


def test_freeze_preserves_exact_lineage_without_consuming_holdout(research):
    trial=completed(research);db,repo,project,_,_,_=research;service=Candidates(db)
    before=repo.get(project['id'])['datasets']
    candidate=service.freeze(project['id'],trial['id'],2,'Investigate removal of entries')
    assert candidate['state']=='FROZEN' and not candidate['validation_granted']
    assert candidate['snapshot']['configuration']['strategy_params']=={'skip':1}
    assert candidate['snapshot_hash']==digest(candidate['snapshot'])
    assert candidate['snapshot']['robustness']['verdict']=='VALIDATION_REQUIRED'
    assert candidate['snapshot']['robustness']['summary']['n']==0
    assert repo.get(project['id'])['datasets']==before
    assert service.freeze(project['id'],trial['id'],2,candidate['reason'])==candidate
    with pytest.raises(ValueError,match='different rationale'):service.freeze(project['id'],trial['id'],2,'Overwrite')
    assert len(service.list(project['id']))==1


def test_assessment_records_missing_neighbors_and_periods_without_ranking(research):
    trial=completed(research);report=robustness(trial,1)
    assert len(report['neighbors'])==1 and report['neighbors'][0]['cell']==2
    assert report['neighbor_coverage']==[{'parameter':'skip','side':'lower','tested':False,'value':None},{'parameter':'skip','side':'upper','tested':True,'value':1}]
    assert report['periods']['year'][0]['period']=='2026'
    assert not report['automatic_promotion']
    assert any('Low sample' in w for w in report['warnings'])
    assert any('Incomplete neighborhood' in w for w in report['warnings'])
    assert report['fee_stress']['limitation'].startswith('Arithmetic')


def test_two_axis_neighbors_hold_the_other_axis_fixed(research):
    trial=completed(research);prototype=trial['cells'][1];trial=deepcopy(trial)
    trial['hypothesis']['axes']=[{'parameter':'a','values':[1,2,3]},{'parameter':'b','values':[10,20,30]}]
    trial['cells']=[{**deepcopy(prototype),'index':i,'payload':{'strategy_params':{'a':a,'b':b}}} for i,(a,b) in enumerate(( (a,b) for a in [1,2,3] for b in [10,20,30]),1)]
    report=robustness(trial,5)
    assert {n['cell'] for n in report['neighbors']}=={2,4,6,8}
    assert all(c['tested'] for c in report['neighbor_coverage'])


def test_frozen_candidate_stops_authorized_loop_and_blocks_new_authorization(research):
    trial=completed(research);db,_,project,hypothesis,jobs,_=research
    loop=ResearchLoop(db,jobs,priced_model(db,project,hypothesis),start_thread=False)
    loop.start(project['id'],1)
    Candidates(db).freeze(project['id'],trial['id'],1,'Review parity first')
    assert loop.get(project['id'])['status']=='STOPPED'
    assert not loop.permitted(loop.get(project['id']))
    with pytest.raises(ValueError,match='Candidate frozen'):loop.start(project['id'],1)


def test_tampered_parameters_and_control_cannot_be_frozen(research):
    trial=completed(research);db,_,project,_,_,_=research;service=Candidates(db)
    with pytest.raises(ValueError,match='variant'):service.freeze(project['id'],trial['id'],0,'Control')
    with db.connect() as c:
        rid=trial['cells'][1]['run_id'];row=c.execute('SELECT config_json FROM backtest_runs WHERE id=?',(rid,)).fetchone()
        config=json.loads(row[0]);config['strategy_params']={'skip':99}
        c.execute('UPDATE backtest_runs SET config_json=? WHERE id=?',(json.dumps(config),rid))
    with pytest.raises(ValueError,match='scope changed'):service.freeze(project['id'],trial['id'],1,'Changed')
    assert not service.list(project['id'])


def test_candidate_api_requires_acknowledgement_and_rejects_payload_overrides(research):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.research_agent import router
    trial=completed(research);db,_,project,_,_,_=research
    app=FastAPI();app.state.services=SimpleNamespace(database=db);app.include_router(router)
    path='/strategy-lab/research-agent/'+project['id']+'/candidates'
    payload={'trial_id':trial['id'],'cell_index':1,'reason':'Review'}
    with TestClient(app) as client:
        assert client.post(path,json=payload).status_code==422
        payload['acknowledgement']='Freeze this development candidate without consuming holdout data'
        assert client.post(path,json={**payload,'strategy_params':{'skip':99}}).status_code==422
        result=client.post(path,json=payload)
        assert result.status_code==200,result.text
        assert client.get(path).json()['items'][0]['id']==result.json()['id']
