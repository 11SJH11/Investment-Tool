from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
import pytest

from app.services.simulation_budget import SimulationBudget
from app.services.backtest_jobs import BacktestJobs, JobCancelled
from tests.test_parent_research import parent, wait_terminal
from tests.test_research_infrastructure import services, base, facts


def wait_for(predicate):
    deadline=monotonic()+5
    while not predicate():
        if monotonic()>deadline: pytest.fail('budget state timed out')
        sleep(.01)


def test_shared_reservations_never_multiply_pool_requests():
    budget=SimulationBudget(lambda:4); release=Event(); entered=Event()
    def first():
        with budget.reserve(3) as n:
            assert n==3; entered.set(); release.wait(5)
    with ThreadPoolExecutor(3) as pool:
        a=pool.submit(first); assert entered.wait(5)
        with budget.reserve(4) as n:
            assert n==1 and budget.snapshot()['used_workers']==4
            with budget.reserve(1) as nested: assert nested==1
        release.set(); a.result()
    assert budget.snapshot()['used_workers']==0 and budget.peak==4


def test_cancelled_waiter_and_failed_owner_release_slots():
    budget=SimulationBudget(lambda:1); cancelled=Event()
    def check():
        if cancelled.is_set(): raise JobCancelled()
    def waiter():
        with budget.reserve(1,check): pytest.fail('cancelled work admitted')
    with ThreadPoolExecutor(1) as pool:
        with budget.reserve(1):
            future=pool.submit(waiter); wait_for(lambda:budget.waiting==1)
            cancelled.set();budget.notify()
            with pytest.raises(JobCancelled):future.result(timeout=5)
    with pytest.raises(RuntimeError):
        with budget.reserve(1): raise RuntimeError('fixture')
    assert budget.used==0 and budget.waiting==0


def test_lower_budget_drains_existing_reservations_before_new_admission():
    limit=[4];budget=SimulationBudget(lambda:limit[0]); entered=Event()
    def next_run():
        with budget.reserve(1):entered.set()
    with ThreadPoolExecutor(1) as pool:
        with budget.reserve(4):
            limit[0]=1;future=pool.submit(next_run)
            wait_for(lambda:budget.waiting==1)
            assert not entered.is_set() and budget.used==4
        future.result(timeout=5)
    assert entered.is_set() and budget.used==0


def test_multiple_real_research_parents_and_ordinary_run_share_one_budget(tmp_path):
    service,_,_=services(tmp_path);queue=BacktestJobs(service.runs.database,service,workers=2)
    try:
        a=parent(4); b=parent(4)
        b['experiment_group']='research:second'
        for child in b['research_children']: child['experiment_group']='research:second'
        jobs=queue.enqueue([a,b,{**base(),'run_name':'ordinary'}],'mixed')
        terminal=[wait_terminal(queue,j['id']) for j in jobs]
        assert all(j['status']=='completed' for j in terminal), terminal
        assert queue.budget.peak<=queue.workers
        assert queue.compute_settings()['used_workers']==0
        assert queue.compute_settings()['queued_simulations']==0
        for payload in (a,b):
            document=queue.research.get(payload['experiment_group'])
            assert document['performance']['workers']<=queue.workers
            for cell,child in zip(document['cells'],payload['research_children']):
                saved=service.get_run(cell['run_id'])
                assert facts(saved['result'])==facts(service.run({**child,'save_run':False}))
    finally:queue.close()


def test_direct_service_run_uses_application_budget_after_preparation(tmp_path):
    service,_,_=services(tmp_path);queue=BacktestJobs(service.runs.database,service,workers=1)
    prepared=service.prepare(base())
    try:
        with ThreadPoolExecutor(1) as pool:
            with queue.budget.reserve(1):
                future=pool.submit(service.run,{**base(),'save_run':False},prepared=prepared)
                wait_for(lambda:queue.budget.waiting==1)
                assert not future.done()
            result=future.result(timeout=15)
        assert result['trades'] and queue.budget.peak==1 and queue.budget.used==0
    finally:queue.close()
