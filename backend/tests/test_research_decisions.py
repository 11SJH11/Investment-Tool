from copy import deepcopy
import json
from types import SimpleNamespace
import pytest
from tests.test_research_trials import research
from tests.test_research_validation import frozen
from app.research_agent.decisions import Decisions
from app.research_agent.validation import Validations
from app.research_agent.analysis import compare
from app.storage.backtest_run_repository import BacktestRunRepository

ACK='Record this research decision; it does not authorize live trading'


def request(kind='REJECTED'):
    return {'decision':kind,'reason':'Fixture evidence reviewed','acknowledgement':ACK,
        'review':{key:'Reviewed fixture; limitations retained' for key in ('periods','winner_retention','parameter_sensitivity','costs_and_regimes','complexity_and_limitations')} if kind=='ACCEPTED_FOR_RESEARCH' else None}


def passing(frozen):
    # Persist explicit synthetic evidence; real engine execution is covered by validation tests.
    (db,_,project,_,jobs,service),candidate=frozen;jobs.trial_coordinator.close();Validations(db)
    records=[];cells=[]
    for index in (0,1):
        original=service.runs.get(candidate['run_id']);config=deepcopy(original['config']);result=deepcopy(original['result'])
        config.update(start_date='2027-01-01',end_date='2027-12-31',market_data_fingerprint='validation-fixture',research_validation_id='validation',research_validation_cell=index)
        result['trades']=[{'symbol':'QQQ','direction':'long','entry_time':f'2027-01-0{4+i}T14:30:00+00:00','exit_time':f'2027-01-0{4+i}T14:35:00+00:00','net_pnl':r,'r_multiple':r,'exit_reason':'fixture'} for i,r in enumerate((2,-1))]
        result['metrics']={'fixture':True};result['equity_curve']=[]
        run=BacktestRunRepository(db).create(config=config,result=result,test_role='validation');records.append(service.runs.get(run['id']))
        cells.append({'index':index,'run_id':run['id'],'payload':config,'status':'COMPLETED'})
    document={'id':'validation','candidate_id':candidate['id'],'candidate_hash':candidate['snapshot_hash'],'project_id':project['id'],
        'status':'COMPLETED','verdict':'VALIDATION_PASS','data_fingerprint':'validation-fixture','criteria':{'minimum_trades':2,'minimum_average_r':.1,'minimum_profit_factor_r':1.1},'cells':cells,'comparison':compare(*records)}
    with db.connect() as c:
        c.execute('INSERT INTO agent_validations VALUES (?,?,?,?)',('validation',project['id'],candidate['id'],json.dumps(document)))
        dataset=deepcopy(project['datasets'][1]);dataset['state']='INSPECTED_VALIDATION'
        c.execute('UPDATE agent_datasets SET document=? WHERE id=?',(json.dumps(dataset),dataset['id']))
        c.execute('INSERT INTO agent_events(project_id,dataset_id,action,detail) VALUES (?,?,?,?)',(project['id'],dataset['id'],'candidate_validation_approved',json.dumps({'validation_id':'validation','candidate_hash':candidate['snapshot_hash'],'criteria':document['criteria']})))
    return document


def test_rejection_preserves_snapshot_and_blocks_later_validation(frozen):
    (db,_,project,_,_,_),candidate=frozen;service=Decisions(db)
    record=service.record(project['id'],candidate['id'],request())
    assert record['decision']=='REJECTED' and record['candidate_hash']==candidate['snapshot_hash']
    assert service.record(project['id'],candidate['id'],request())==record
    with pytest.raises(ValueError,match='immutable'):service.record(project['id'],candidate['id'],{**request(),'reason':'Different'})
    with pytest.raises(ValueError,match='final research decision'):Validations(db).approve(project['id'],candidate['id'],project['datasets'][1]['id'],{})
    from app.research_agent.candidates import Candidates
    assert Candidates(db).list(project['id'])[0]==candidate


def test_acceptance_requires_passing_validation_and_structured_review(frozen):
    (db,_,project,_,_,_),candidate=frozen;service=Decisions(db)
    with pytest.raises(ValueError,match='structured'):service.record(project['id'],candidate['id'],{**request('ACCEPTED_FOR_RESEARCH'),'review':None})
    with pytest.raises(ValueError,match='passing validation'):service.record(project['id'],candidate['id'],request('ACCEPTED_FOR_RESEARCH'))
    assert not service.list(project['id'])


def test_acceptance_reverifies_saved_evidence_and_records_limits(frozen):
    validation=passing(frozen);(db,_,project,_,_,_),candidate=frozen
    result=Decisions(db).record(project['id'],candidate['id'],request('ACCEPTED_FOR_RESEARCH'))
    assert result['decision']=='ACCEPTED_FOR_RESEARCH' and result['validation_id']==validation['id']
    assert result['development_warnings']==candidate['snapshot']['robustness']['warnings']
    assert 'no strategy replacement' in result['scope']


def test_changed_validation_result_blocks_acceptance(frozen):
    validation=passing(frozen);(db,_,project,_,_,_),candidate=frozen
    with db.connect() as c:
        rid=validation['cells'][1]['run_id'];r=json.loads(c.execute('SELECT result_json FROM backtest_runs WHERE id=?',(rid,)).fetchone()[0]);r['trades'][0]['r_multiple']=100
        c.execute('UPDATE backtest_runs SET result_json=? WHERE id=?',(json.dumps(r),rid))
    with pytest.raises(ValueError,match='evidence changed'):Decisions(db).record(project['id'],candidate['id'],request('ACCEPTED_FOR_RESEARCH'))


def test_recorded_pass_cannot_override_failing_criteria(frozen):
    validation=passing(frozen);(db,_,project,_,_,_),candidate=frozen
    validation['criteria']['minimum_trades']=30
    with db.connect() as c:c.execute('UPDATE agent_validations SET document=?',(json.dumps(validation),))
    with pytest.raises(ValueError,match='Approved validation criteria'):Decisions(db).record(project['id'],candidate['id'],request('ACCEPTED_FOR_RESEARCH'))


def test_api_requires_acknowledgement_and_stores_decision(frozen):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.research_agent import router
    (db,_,project,_,_,_),candidate=frozen
    app=FastAPI();app.state.services=SimpleNamespace(database=db);app.include_router(router)
    path='/strategy-lab/research-agent/'+project['id']
    with TestClient(app) as client:
        body=request();body.pop('acknowledgement')
        assert client.post(path+'/candidates/'+candidate['id']+'/decision',json=body).status_code==422
        response=client.post(path+'/candidates/'+candidate['id']+'/decision',json=request())
        assert response.status_code==200,response.text
        assert client.get(path+'/decisions').json()['items'][0]['decision']=='REJECTED'
