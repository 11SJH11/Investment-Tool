from copy import deepcopy
from time import monotonic, sleep

import pytest

from app.services.research_experiments import children
from app.services.backtest_jobs import BacktestJobs, JobCancelled
from app.services.research_runner import run_experiment
from app.storage.research_experiment_repository import ResearchExperimentRepository
from tests.test_research_infrastructure import services,base,axes,facts


def parent(workers=1):
    plan,runs=children(base(),axes(),'parent','Interaction fixture',role='development')
    return {**base(),'experiment_type':'interaction','experiment_group':'research:parent',
            'run_name':'Interaction fixture','test_role':'development','research_workers':workers,
            'research_plan':plan,'research_base':base(),'research_children':runs}


def wait_terminal(queue,id):
    deadline=monotonic()+40
    while monotonic()<deadline:
        job=queue.get(id)
        if job['status'] in ('completed','failed','cancelled'):return job
        sleep(.03)
    pytest.fail('Parent did not reach a terminal state')


@pytest.mark.parametrize('workers',[1,2])
def test_one_parent_prepare_once_exact_children_and_persistence(tmp_path,workers):
    service,market,provider=services(tmp_path)
    original=service.prepare;prepares=[]
    def tracked(*a,**kw):prepares.append(1);return original(*a,**kw)
    service.prepare=tracked
    queue=BacktestJobs(service.runs.database,service,workers=1)
    try:
        payload=parent(workers);jobs=queue.enqueue([payload],'one-parent')
        job=wait_terminal(queue,jobs[0]['id'])
        assert job['status']=='completed',job
        assert len(queue.list())==1 and prepares==[1]
        assert (job['processed'],job['total'])==(4,4)
        document=queue.research.get(payload['experiment_group'])
        assert document['experiment_type']=='interaction' and document['test_role']=='development'
        assert document['market_data_fingerprint']
        assert len({c['run_id'] for c in document['cells']})==4
        assert service.list_runs()==[]  # Children remain accessible through their parent.
        for cell,child in zip(document['cells'],payload['research_children']):
            saved=service.get_run(cell['run_id'])
            assert facts(saved['result'])==facts(service.run({**child,'save_run':False}))
            assert saved['config']['market_data_fingerprint']==document['market_data_fingerprint']
        queue.clear_finished()
        assert service.get_experiment(payload['experiment_group'])['experiment']['status']=='completed'
    finally:queue.close()


def test_partial_failure_and_resume_without_duplicate_saved_cells(tmp_path,monkeypatch):
    service,_,_=services(tmp_path);repository=ResearchExperimentRepository(service.runs.database)
    import app.services.research_runner as runner
    real=runner.execute_cell;fail=[True]
    def execute(payload,*a,**kw):
        if fail[0] and payload['research_experiment']['cell_index']==1:return {'error':'Fixture failure'}
        return real(payload,*a,**kw)
    monkeypatch.setattr(runner,'execute_cell',execute)
    kw=dict(progress=lambda *a:None,cancelled=lambda:None,commit=lambda f:f())
    first=run_experiment(service,repository,parent(),**kw)
    assert first['status']=='failed' and first['cells'][1]['error']=='Fixture failure'
    ids=[c.get('run_id') for c in first['cells']]
    fail[0]=False
    second=run_experiment(service,repository,parent(),**kw)
    assert second['status']=='completed'
    assert [second['cells'][i]['run_id'] for i in (0,2,3)]==[ids[i] for i in (0,2,3)]
    assert len(service.runs.list_by_experiment('research:parent'))==4


def test_cancel_preserves_saved_cells_and_changed_source_cannot_mix(tmp_path):
    service,market,provider=services(tmp_path);repository=ResearchExperimentRepository(service.runs.database)
    cancelled=[False]
    def check():
        if cancelled[0]:raise JobCancelled()
    def progress(status,done,total):
        if done==1:cancelled[0]=True
    with pytest.raises(JobCancelled):
        run_experiment(service,repository,parent(),progress=progress,cancelled=check,commit=lambda f:f())
    doc=repository.get('research:parent')
    assert doc['status']=='cancelled' and doc['cells'][0]['status']=='completed'
    assert len(service.runs.list_by_experiment('research:parent'))==1
    cancelled[0]=False
    # Changed durable input must not silently merge with a completed cell.
    provider.cache_namespace='changed-source'
    with pytest.raises(ValueError,match='input changed'):
        run_experiment(service,repository,parent(),progress=lambda *a:None,cancelled=check,commit=lambda f:f())


def test_restart_does_not_mark_partial_parent_completed(tmp_path):
    service,_,_=services(tmp_path);db=service.runs.database
    queue=BacktestJobs(db,service,workers=1);queue.close()
    payload=parent()
    import json
    with db.connect() as c:
        c.execute("INSERT INTO backtest_jobs(id,request_key,ordinal,batch_id,payload,status) VALUES('interrupted','r',0,'r',?,'running')",(json.dumps(payload),))
    restarted=BacktestJobs(db,service,workers=1)
    try:
        assert restarted.get('interrupted')['status']=='failed'
        assert 'resumes' in restarted.get('interrupted')['error']
    finally:restarted.close()


def test_saved_outputs_cannot_mutate_shared_inputs(tmp_path):
    service,_,_=services(tmp_path);payload=base();prepared=service.prepare(payload)
    first=service.run({**payload,'save_run':False},prepared=prepared)
    expected=facts(first)
    first['symbols'].append('CONTAMINATED')
    first['data']['providers']['SPY']['provider']='CONTAMINATED'
    first['trades'][0]['metadata']['test']='CONTAMINATED'
    second=service.run({**payload,'save_run':False},prepared=prepared)
    assert second['symbols']==['SPY'] and second['data']['providers']['SPY']['provider']=='fixture'
    assert 'test' not in second['trades'][0]['metadata']


def test_recover_child_saved_before_parent_reference(tmp_path):
    service,_,_=services(tmp_path);repository=ResearchExperimentRepository(service.runs.database)
    kw=dict(progress=lambda *a:None,cancelled=lambda:None,commit=lambda f:f())
    first=run_experiment(service,repository,parent(),**kw)
    expected=[c['run_id'] for c in first['cells']]
    first['cells'][1]={'index':1,'values':[-1,1],'status':'running'}
    first['status']='running';repository.save(first)
    again=run_experiment(service,repository,parent(),**kw)
    assert [c['run_id'] for c in again['cells']]==expected
    assert len(service.runs.list_by_experiment('research:parent'))==4


def test_process_cancellation_event_is_observed_without_provider_access(tmp_path):
    import multiprocessing
    import pickle
    from concurrent.futures import ProcessPoolExecutor
    from app.research_runtime import initialize_worker,execute_cell
    service,_,_=services(tmp_path);inputs=service.prepare(base())
    path=tmp_path/'prepared.pkl';path.write_bytes(pickle.dumps(inputs))
    context=multiprocessing.get_context('spawn');event=context.Event();event.set()
    with ProcessPoolExecutor(max_workers=1,mp_context=context,initializer=initialize_worker,initargs=(str(path),event)) as pool:
        assert pool.submit(execute_cell,base()).result(timeout=20)=={'cancelled':True}


def test_api_preview_and_submit_create_one_parent_and_keep_type_separate(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from app.api.strategy_lab import router
    from app.api.dependencies import get_services
    service,_,_=services(tmp_path);queue=BacktestJobs(service.runs.database,service,workers=1)
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[get_services]=lambda:SimpleNamespace(backtest=service,backtest_jobs=queue)
    try:
        with TestClient(app) as client:
            body={'base':base(),'axes':axes(),'request_key':'api','workers':1,'name':'Interaction research','role':'development'}
            preview=client.post('/strategy-lab/research-experiments/preview',json=body)
            assert preview.status_code==200 and preview.json()['job_count']==4
            response=client.post('/strategy-lab/research-experiments',json=body)
            assert response.status_code==200
            jobs=response.json()['jobs'];assert len(jobs)==1
            assert jobs[0]['payload']['experiment_type']=='interaction'
            assert jobs[0]['payload']['test_role']=='development'
            assert wait_terminal(queue,jobs[0]['id'])['status']=='completed'
            again=client.post('/strategy-lab/research-experiments',json=body)
            assert again.json()['jobs'][0]['id']==jobs[0]['id']
            doc=client.get('/strategy-lab/experiments/research:api').json()
            assert len(doc['runs'])==4 and doc['experiment']['plan']['job_count']==4
            assert len(client.get('/strategy-lab/research-experiments').json()['experiments'])==1
    finally:queue.close()


def test_same_parent_cannot_have_overlapping_retries(tmp_path):
    from threading import Event
    service,_,_=services(tmp_path);release=Event();entered=Event();original=service.prepare
    def prepare(*args,**kwargs):
        entered.set();release.wait(10);return original(*args,**kwargs)
    service.prepare=prepare;queue=BacktestJobs(service.runs.database,service,workers=2)
    try:
        queue.enqueue([parent()],'first');assert entered.wait(5)
        with pytest.raises(ValueError,match='already queued or running'):
            queue.enqueue([parent()],'duplicate')
    finally:release.set();queue.close()
