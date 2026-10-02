import json
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.strategy_lab import router
from app.api.dependencies import get_services
from app.services.backtest_jobs import BacktestJobs
from app.services.research_status import experiment_status, cell_metrics
from app.storage.research_experiment_repository import ResearchExperimentRepository
from tests.test_parent_research import parent, wait_terminal
from tests.test_research_infrastructure import services


def test_compact_endpoints_preserve_full_snapshots_and_metrics(tmp_path):
    service,_,_=services(tmp_path);queue=BacktestJobs(service.runs.database,service,workers=1)
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[get_services]=lambda:SimpleNamespace(backtest=service,backtest_jobs=queue)
    try:
        job=queue.enqueue([parent()], 'compact')[0]
        assert wait_terminal(queue,job['id'])['status']=='completed'
        before=service.get_experiment('research:parent')
        with TestClient(app) as client:
            full=client.get('/strategy-lab/jobs').json()
            compact=client.get('/strategy-lab/jobs?compact=true').json()
            assert compact['jobs'][0]['payload']['research_count']==4
            assert 'research_children' not in compact['jobs'][0]['payload']
            assert 'strategy_params' not in compact['jobs'][0]['payload']
            assert len(json.dumps(compact))<len(json.dumps(full))/2
            detail=client.get('/strategy-lab/experiments/research:parent?compact=true').json()
            assert detail['runs']==[] and len(detail['experiment']['cells'])==4
            status=client.get('/strategy-lab/experiments/research:parent/status').json()
            assert 'plan' not in status and 'performance' not in status and 'base_configuration' not in status
            for cell,run in zip(sorted(status['cells'],key=lambda c:c['run_id']), sorted(before['runs'],key=lambda r:r['id'])):
                metrics=cell['metrics'];expected=run['result']['metrics']
                for key,value in expected.items(): assert metrics[key]==value
                trades=run['result']['trades']
                assert metrics['average_mfe']==(sum(t['metadata']['mfe_r'] for t in trades)/len(trades) if trades else None)
            history=client.get('/strategy-lab/research-experiments?compact=true').json()['experiments'][0]
            assert history['completed']==history['total']==4
            assert 'cells' not in history and 'plan' not in history
            assert 'strategy_params' not in history['base_configuration']
            assert client.get('/strategy-lab/experiments/missing/status').status_code==404
            assert client.get('/strategy-lab/experiments/research:parent').json()['runs']
            assert client.get('/strategy-lab/runs/'+str(status['cells'][0]['run_id'])).json()['result']['trades']
        assert service.get_experiment('research:parent')==before
    finally:queue.close()


def test_projected_diagnostics_preserve_fallbacks_nulls_and_boolean_types(tmp_path):
    service,_,_=services(tmp_path);db=service.runs.database
    trades=[{'metadata':{'mfe_r':True,'mfe_r_lower_bound':2,'mae_r':None,'mae_r_lower_bound':.5},'exit_reason':'stop_loss'},
            {'source_metadata':{'mfe_r':4,'mae_r':1},'exit_reason':'take_profit'},
            {'metadata':{},'source_metadata':{'mfe_r':999},'exit_reason':'session_close'}]
    run=service.runs.create(config={'symbols':['SPY']},result={'trades':trades,'metrics':{'trades':3}},experiment_group='legacy')
    ResearchExperimentRepository(db).save({'experiment_group':'legacy','status':'completed','cells':[{'index':0,'run_id':run['id'],'status':'completed'}]})
    metrics=experiment_status(db,'legacy')['cells'][0]['metrics']
    assert metrics['average_mfe']==3 and metrics['mfe_n']==2
    assert metrics['average_mae']==.75 and metrics['mae_n']==2
    assert metrics['stop_pct']==metrics['target_pct']==100/3
    empty=cell_metrics({},[])
    assert empty['average_mfe'] is None and empty['stop_pct'] is None and empty['mfe_n']==0
