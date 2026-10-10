from copy import deepcopy
import pytest
from tests.test_research_trials import research, terminal
from tests.test_research_validation import frozen
from tests.test_backtest_jobs import wait_for
from app.research_agent.regimes import approve, report, ACK, validate_identity
from app.research_agent.trials import Trials
from app.research_agent.feedback import development_feedback
from app.research_agent.decisions import Decisions


def request(candidate):
    config=candidate['snapshot']['configuration']
    return {'scenarios':[{'name':'Declared fixture regime','start':config['start_date'],'end':config['end_date'],'definition':'Fixture-only range, not a market classification','evidence_source':'Synthetic fixture known before reruns'}],'rationale':'Paired engine regression','acknowledgement':ACK}


def test_real_engine_pairs_idempotence_and_frozen_candidate_preserved(frozen):
    (db,repo,project,_,jobs,service),candidate=frozen
    before=service.runs.get(candidate['run_id']);payload=request(candidate)
    trial=approve(db,project['id'],candidate['id'],payload);trials=Trials(db)
    wait_for(lambda:terminal(trials,trial['id']))
    done=trials.get(trial['id']);assert done['status']=='COMPLETED',done
    assert done['control_parity'] is True
    assert [c['role'] for c in done['cells']]==['control','regime_baseline','regime_candidate']
    output=report(db,project['id'],candidate['id']);assert len(output['rows'])==3
    assert output['rows'][2]['path']['retained']>=0
    assert service.runs.get(candidate['run_id'])==before
    assert approve(db,project['id'],candidate['id'],payload)['id']==trial['id']
    assert repo.get(project['id'])['datasets'][1]['state']=='LOCKED_HOLDOUT'
    assert 'trial/'+trial['id'] not in development_feedback(db,repo.get(project['id']))[0]
    changed=deepcopy(payload);changed['rationale']='After observing results'
    with pytest.raises(ValueError,match='immutable'):approve(db,project['id'],candidate['id'],changed)


@pytest.mark.parametrize('mutation',['outside','overlap','reversed'])
def test_invalid_regime_ranges_do_not_reserve_jobs(frozen,mutation):
    (db,_,project,_,jobs,_),candidate=frozen;jobs.trial_coordinator.close()
    payload=request(candidate)
    if mutation=='outside':payload['scenarios'][0]['start']='1900-01-01'
    elif mutation=='reversed':payload['scenarios'][0]['end']='1900-01-01'
    else:payload['scenarios'].append({**payload['scenarios'][0],'name':'Overlapping'})
    with pytest.raises(ValueError):approve(db,project['id'],candidate['id'],payload)
    assert not any(t.get('kind')=='regime' for t in Trials(db).list(project['id']))


def test_regime_identity_cannot_change_between_pair_or_retry(frozen):
    (db,_,project,_,jobs,_),candidate=frozen;jobs.trial_coordinator.close()
    trial=approve(db,project['id'],candidate['id'],request(candidate))
    with pytest.raises(ValueError,match='baseline'):validate_identity(db,trial,trial['cells'][2]['payload'],'first')
    validate_identity(db,trial,trial['cells'][1]['payload'],'first')
    with pytest.raises(ValueError,match='fingerprint'):validate_identity(db,trial,trial['cells'][2]['payload'],'changed')
    with pytest.raises(ValueError,match='fingerprint'):validate_identity(db,trial,trial['cells'][1]['payload'],'changed')


def test_unfinished_regime_blocks_final_decision(frozen):
    (db,_,project,_,jobs,_),candidate=frozen;jobs.trial_coordinator.close()
    approve(db,project['id'],candidate['id'],request(candidate))
    with pytest.raises(ValueError,match='regime trials'):
        Decisions(db).record(project['id'],candidate['id'],{'decision':'REJECTED','reason':'Fixture','acknowledgement':'Record this research decision; it does not authorize live trading'})


def test_regime_api_requires_consent_and_preserves_paused_plan(frozen):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from app.api.research_agent import router
    (db,_,project,_,jobs,_),candidate=frozen;jobs.trial_coordinator.close()
    app=FastAPI();app.include_router(router);app.state.services=SimpleNamespace(database=db)
    path=f"/strategy-lab/research-agent/{project['id']}/candidates/{candidate['id']}/regimes"
    payload=request(candidate)
    with TestClient(app) as client:
        assert client.post(path,json={k:v for k,v in payload.items() if k!='acknowledgement'}).status_code==422
        response=client.post(path,json=payload);assert response.status_code==200
        trial=response.json()
        Trials(db).transition(trial['id'],'pause',jobs)
        assert client.get(path).json()['status']=='PAUSED'
        assert client.post(path,json=payload).json()['id']==trial['id']


def test_different_candidate_parameters_are_compared_to_original_baseline(frozen):
    from app.research_agent.candidates import Candidates
    (db,_,project,_,_,_),first=frozen
    candidate=Candidates(db).freeze(project['id'],first['trial_id'],2,'Skip-entry candidate for paired regression')
    trial=approve(db,project['id'],candidate['id'],request(candidate));trials=Trials(db)
    wait_for(lambda:terminal(trials,trial['id']))
    assert trials.get(trial['id'])['status']=='COMPLETED'
    output=report(db,project['id'],candidate['id'])
    assert output['rows'][1]['summary']['n']==1
    assert output['rows'][2]['summary']['n']==0
    assert output['rows'][2]['path']['removed']['n']==1
