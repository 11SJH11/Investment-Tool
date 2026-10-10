from copy import deepcopy
import json
import pytest
from tests.test_research_trials import research, terminal
from tests.test_research_validation import frozen
from tests.test_backtest_jobs import wait_for
from app.research_agent.costs import approve, report, CostApproval
from app.research_agent.trials import Trials, validate
from app.research_agent.candidates import Candidates
from app.research_agent.feedback import development_feedback
from app.research_agent.decisions import Decisions

ACK='Run the frozen candidate control and declared development cost scenarios'

def request():
    return dict(scenarios=[dict(name='Commission',commission_per_order=5,spread_bps=0,slippage_bps=0),dict(name='Spread and slippage',commission_per_order=5,spread_bps=2,slippage_bps=1)],rationale='Declared fixture costs',acknowledgement=ACK)


def test_costs_use_real_engine_control_and_preserve_frozen_data(frozen):
    (db,repo,project,_,jobs,service),candidate=frozen
    original=service.runs.get(candidate['run_id'])
    trial=approve(db,project['id'],candidate['id'],request());trials=Trials(db)
    wait_for(lambda:terminal(trials,trial['id']))
    result=trials.get(trial['id']);assert result['status']=='COMPLETED',result
    assert result['control_parity'] is True
    output=report(db,project['id'],candidate['id'])
    assert len(output['rows'])==3
    control,commission,slippage=output['rows']
    assert control['money']['fees']==0
    assert commission['money']['fees']==10
    assert commission['money']['net_pnl']==pytest.approx(commission['money']['gross_pnl']-10)
    assert slippage['money']['gross_pnl']<control['money']['gross_pnl']
    assert service.runs.get(candidate['run_id'])==original
    assert Candidates(db).list(project['id'])[0]==candidate
    assert repo.get(project['id'])['datasets'][1]['state']=='LOCKED_HOLDOUT'
    assert approve(db,project['id'],candidate['id'],request())['id']==trial['id']
    changed=request();changed['rationale']='Changed after results'
    with pytest.raises(ValueError,match='immutable'):approve(db,project['id'],candidate['id'],changed)
    feedback,_=development_feedback(db,repo.get(project['id']))
    assert 'trial/'+trial['id'] not in feedback
    with pytest.raises(ValueError,match='Completed development'):Candidates(db).assess(project['id'],trial['id'],1)


def test_cost_payload_and_control_gate_reject_forgery(frozen):
    (db,_,project,_,jobs,_),candidate=frozen;jobs.trial_coordinator.close()
    trial=approve(db,project['id'],candidate['id'],request())
    altered={**trial['cells'][0]['payload'],'start_date':'2027-01-01'}
    with pytest.raises(ValueError,match='Payload differs'):validate(db,altered)
    with pytest.raises(ValueError,match='Control parity'):validate(db,trial['cells'][1]['payload'])
    assert not any(j['payload'].get('research_trial_id')==trial['id'] for j in jobs.list())


def test_changed_data_blocks_cost_variants(frozen):
    (db,_,project,_,_,service),candidate=frozen;service.changed=True
    trial=approve(db,project['id'],candidate['id'],request());trials=Trials(db)
    wait_for(lambda:terminal(trials,trial['id']))
    result=trials.get(trial['id'])
    assert result['status']=='PAUSED' and result['control_parity'] is None
    assert all(c['status']=='PENDING' for c in result['cells'][1:])


def test_budget_and_strict_scenario_validation(frozen):
    (db,_,project,_,_,_),candidate=frozen
    for edit in [dict(spread_bps=-1),dict(spread_bps=float('nan')),dict(start_date='2027-01-01')]:
        value=request();value['scenarios'][0].update(edit)
        with pytest.raises(ValueError):CostApproval.model_validate(value)
    same=request();same['scenarios'][1]=deepcopy(same['scenarios'][0])
    with pytest.raises(ValueError,match='unique'):approve(db,project['id'],candidate['id'],same)
    with db.connect() as c:
        p=json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?',(project['id'],)).fetchone()[0]);p['research_budget']['max_trial_runs']=4
        c.execute('UPDATE agent_projects SET document=? WHERE id=?',(json.dumps(p),project['id']))
    with pytest.raises(ValueError,match='budget'):approve(db,project['id'],candidate['id'],request())


def test_decision_waits_for_cost_trial_and_retains_evidence(frozen):
    (db,_,project,_,jobs,_),candidate=frozen;jobs.trial_coordinator.close()
    trial=approve(db,project['id'],candidate['id'],request());trials=Trials(db)
    payload=dict(decision='REJECTED',reason='Stop research',acknowledgement='Record this research decision; it does not authorize live trading')
    with pytest.raises(ValueError,match='Finish or cancel'):Decisions(db).record(project['id'],candidate['id'],payload)
    trials.transition(trial['id'],'cancel',jobs)
    decision=Decisions(db).record(project['id'],candidate['id'],payload)
    assert decision['cost_evidence'][0]['status']=='CANCELLED'
    assert all(r['status']=='PENDING' for r in decision['cost_evidence'][0]['rows'])


def test_saved_cost_results_reverified(frozen):
    (db,_,project,_,_,_),candidate=frozen
    trial=approve(db,project['id'],candidate['id'],request());trials=Trials(db)
    wait_for(lambda:terminal(trials,trial['id']))
    result=trials.get(trial['id']);assert result['status']=='COMPLETED'
    with db.connect() as c:
        run_id=result['cells'][1]['run_id'];saved=json.loads(c.execute('SELECT result_json FROM backtest_runs WHERE id=?',(run_id,)).fetchone()[0]);saved['metrics']['tampered']=1
        c.execute('UPDATE backtest_runs SET result_json=? WHERE id=?',(json.dumps(saved),run_id))
    with pytest.raises(ValueError,match='evidence changed'):report(db,project['id'],candidate['id'])


def test_cost_trial_pause_resume_and_restart_keep_one_queue_attempt(frozen):
    (db,_,project,_,jobs,_),candidate=frozen;jobs.trial_coordinator.close()
    trial=approve(db,project['id'],candidate['id'],request());trials=Trials(db)
    trials.transition(trial['id'],'pause',jobs)
    resumed=trials.transition(trial['id'],'resume',jobs)
    assert resumed['status']=='ACTIVE'
    jobs.trial_coordinator.tick()
    wait_for(lambda:any(j['payload'].get('research_trial_id')==trial['id'] and j['status']=='completed' for j in jobs.list()))
    # Recreated repository/coordinator state resolves the durable request key.
    jobs.trial_coordinator.repo=Trials(db)
    jobs.trial_coordinator.tick()
    assert trials.get(trial['id'])['control_parity'] is True
    assert len([j for j in jobs.list() if j['payload'].get('research_trial_id')==trial['id']])==1


def test_cost_api_consent_and_ownership(frozen):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.research_agent import router
    (db,_,project,_,jobs,_),candidate=frozen;jobs.trial_coordinator.close()
    app=FastAPI();app.state.services=SimpleNamespace(database=db);app.include_router(router)
    path='/strategy-lab/research-agent/'+project['id']+'/candidates/'+candidate['id']+'/costs'
    with TestClient(app) as client:
        body=request();body.pop('acknowledgement')
        assert client.post(path,json=body).status_code==422
        assert client.get(path).json() is None
        response=client.post(path,json=request());assert response.status_code==200,response.text
        assert client.get(path).json()['trial_id']==response.json()['id']
        assert client.post(path.replace(candidate['id'],'unknown'),json=request()).status_code==400


def test_cost_report_blocks_new_global_holdout_before_reading_results(frozen):
    (db,_,project,_,_,_),candidate=frozen
    trial=approve(db,project['id'],candidate['id'],request());trials=Trials(db)
    wait_for(lambda:terminal(trials,trial['id']))
    assert trials.get(trial['id'])['status']=='COMPLETED'
    with db.connect() as c:
        d=dict(id='foreign',project_id='another-project',symbols=['QQQ'],timeframe='1m',start='2026-01-01',end='2026-01-03',state='LOCKED_HOLDOUT')
        c.execute('INSERT INTO agent_datasets VALUES (?,?)',(d['id'],json.dumps(d)))
        c.execute('UPDATE backtest_runs SET result_json=? WHERE id=?',('invalid result JSON',candidate['run_id']))
    with pytest.raises(ValueError,match='Holdout firewall'):report(db,project['id'],candidate['id'])
