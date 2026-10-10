from copy import deepcopy
from types import SimpleNamespace
import json
import pytest
from app.backtesting.strategies import strategy_registry
from app.backtesting.strategies.base import Strategy, StrategySpec, ParameterSpec
from app.research_agent.simplification import approve, report, scenarios, SimplificationApproval
from app.research_agent.candidates import Candidates
from app.research_agent.decisions import Decisions
from app.research_agent.trials import Trials, validate
from app.research_agent.feedback import development_feedback
from tests.test_research_trials import research, terminal
from tests.test_research_validation import frozen
from tests.test_backtest_jobs import wait_for

ACK='Run one declared rule ablation at a time on development data; off semantics are my responsibility'


def request():
    return dict(scenarios=[dict(name='Disable fixture entries',parameter='skip',off_value=1,rule_removed='Fixture skip=1 disables all entry attempts; verifies execution, not profitable simplification')],rationale='Independent declared rule ablation',acknowledgement=ACK)


def test_real_simplification_control_and_ablation_preserve_candidate_and_costs(frozen):
    (db,repo,project,_,jobs,service),candidate=frozen
    original=service.runs.get(candidate['run_id'])
    trial=approve(db,project['id'],candidate['id'],request());trials=Trials(db)
    wait_for(lambda:terminal(trials,trial['id']))
    result=trials.get(trial['id']);assert result['status']=='COMPLETED',result
    assert result['control_parity'] is True and result['reserved_runs']==2
    assert result['cells'][1]['role']=='ablation'
    control,child=result['cells']
    differing={k for k in control['payload'] if control['payload'][k]!=child['payload'][k]}
    assert differing=={'strategy_params','research_trial_cell'}
    output=report(db,project['id'],candidate['id'])
    assert output['rows'][0]['summary']['n']==1 and output['rows'][1]['summary']['n']==0
    assert output['rows'][1]['removed_winners']['n']==1
    assert output['request']==request()
    assert service.runs.get(candidate['run_id'])==original
    assert Candidates(db).list(project['id'])[0]==candidate
    assert repo.get(project['id'])['datasets'][1]['state']=='LOCKED_HOLDOUT'
    assert approve(db,project['id'],candidate['id'],request())['id']==trial['id']
    changed=request();changed['scenarios'][0]['off_value']=0
    with pytest.raises(ValueError,match='immutable'):approve(db,project['id'],candidate['id'],changed)
    feedback,_=development_feedback(db,repo.get(project['id']))
    assert 'trial/'+trial['id'] not in feedback
    with pytest.raises(ValueError,match='Completed development'):Candidates(db).assess(project['id'],trial['id'],1)


@pytest.fixture
def declared(monkeypatch):
    class Fixture(Strategy):
        spec=StrategySpec(key='ablation_contract_fixture',name='Ablation contract',defaults={'a':True,'b':2,'mode':'filter','text':'free'},parameters=(ParameterSpec('a','Rule A','bool',True),ParameterSpec('b','Rule B','int',2,0,4,1),ParameterSpec('mode','Mode','choice','filter',choices=('filter','off')),ParameterSpec('text','Text','string','free')))
    monkeypatch.setitem(strategy_registry._items,Fixture.spec.key,Fixture)
    return {'strategy_key':Fixture.spec.key,'symbols':['QQQ'],'strategy_params':{'a':True,'b':2,'mode':'filter'}}


def test_each_ablation_starts_from_candidate_not_previous_ablation(declared):
    original=deepcopy(declared)
    payload={'scenarios':[dict(name='A',parameter='a',off_value=False),dict(name='B',parameter='b',off_value=0),dict(name='Mode',parameter='mode',off_value='off')]}
    result=scenarios(declared,payload)
    assert [r['overrides']['strategy_params'] for r in result]==[{'a':False,'b':2,'mode':'filter'},{'a':True,'b':0,'mode':'filter'},{'a':True,'b':2,'mode':'off'}]
    assert declared==original


@pytest.mark.parametrize('parameter,value', [('a',0),('b',False),('b',1.5),('b',5),('mode','unknown'),('text','x'),('missing',0),('a',True)])
def test_invalid_or_noop_off_values_rejected(declared,parameter,value):
    with pytest.raises(ValueError):scenarios(declared,{'scenarios':[dict(name='Bad',parameter=parameter,off_value=value)]})


def test_schema_and_duplicate_rules_cannot_smuggle_execution_changes(declared):
    body=request();body['scenarios'][0]['slippage_bps']=0
    with pytest.raises(ValueError):SimplificationApproval.model_validate(body)
    body=request();body['scenarios'][0]['off_value']=float('nan')
    with pytest.raises(ValueError):SimplificationApproval.model_validate(body)
    body={'scenarios':[dict(name='A',parameter='a',off_value=False),dict(name='Again',parameter='a',off_value=False)]}
    with pytest.raises(ValueError,match='each rule once'):scenarios(declared,body)


def test_simplification_budget_consent_and_payload_gates(frozen):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.research_agent import router
    (db,_,project,_,jobs,_),candidate=frozen;jobs.trial_coordinator.close()
    app=FastAPI();app.state.services=SimpleNamespace(database=db);app.include_router(router)
    path='/strategy-lab/research-agent/'+project['id']+'/candidates/'+candidate['id']+'/simplification'
    with TestClient(app) as client:
        noack=request();noack.pop('acknowledgement')
        assert client.post(path,json=noack).status_code==422
        assert client.get(path).json() is None
        response=client.post(path,json=request());assert response.status_code==200,response.text
        trial=response.json()
        assert client.get(path).json()['trial_id']==trial['id']
        assert client.post(path.replace(candidate['id'],'unknown'),json=request()).status_code==400
    with pytest.raises(ValueError,match='Payload differs'):validate(db,{**trial['cells'][0]['payload'],'start_date':'2027-01-01'})
    with pytest.raises(ValueError,match='Control parity'):validate(db,trial['cells'][1]['payload'])
    from app.research_agent.costs import approve as approve_cost
    from tests.test_research_costs import request as cost_request
    Trials(db).transition(trial['id'],'cancel',jobs)
    with db.connect() as c:
        p=json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?',(project['id'],)).fetchone()[0]);p['research_budget']['max_trial_runs']=6
        c.execute('UPDATE agent_projects SET document=? WHERE id=?',(json.dumps(p),project['id']))
    with pytest.raises(ValueError,match='budget'):approve_cost(db,project['id'],candidate['id'],cost_request())


def test_simplification_data_change_blocks_ablation(frozen):
    (db,_,project,_,_,service),candidate=frozen;service.changed=True
    trial=approve(db,project['id'],candidate['id'],request());trials=Trials(db)
    wait_for(lambda:terminal(trials,trial['id']))
    result=trials.get(trial['id'])
    assert result['status']=='PAUSED' and result['control_parity'] is None
    assert result['cells'][1]['status']=='PENDING'


def test_simplification_pause_resume_and_decision_evidence(frozen):
    (db,_,project,_,jobs,_),candidate=frozen;jobs.trial_coordinator.close()
    trial=approve(db,project['id'],candidate['id'],request());trials=Trials(db)
    trials.transition(trial['id'],'pause',jobs)
    assert trials.transition(trial['id'],'resume',jobs)['status']=='ACTIVE'
    payload=dict(decision='REJECTED',reason='Stop research',acknowledgement='Record this research decision; it does not authorize live trading')
    with pytest.raises(ValueError,match='Finish or cancel'):Decisions(db).record(project['id'],candidate['id'],payload)
    trials.transition(trial['id'],'cancel',jobs)
    decision=Decisions(db).record(project['id'],candidate['id'],payload)
    assert decision['simplification_evidence'][0]['status']=='CANCELLED'
    assert decision['simplification_evidence'][0]['request']==request()


def test_changed_saved_parameters_block_evidence(frozen):
    (db,_,project,_,_,_),candidate=frozen
    trial=approve(db,project['id'],candidate['id'],request());trials=Trials(db)
    wait_for(lambda:terminal(trials,trial['id']))
    result=trials.get(trial['id']);assert result['status']=='COMPLETED'
    with db.connect() as c:
        rid=result['cells'][1]['run_id'];cfg=json.loads(c.execute('SELECT config_json FROM backtest_runs WHERE id=?',(rid,)).fetchone()[0]);cfg['strategy_params']['skip']=0
        c.execute('UPDATE backtest_runs SET config_json=? WHERE id=?',(json.dumps(cfg),rid))
    with pytest.raises(ValueError,match='parameters changed'):report(db,project['id'],candidate['id'])
