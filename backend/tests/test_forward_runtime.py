from datetime import datetime, timezone
import json
import pytest
from app.forward.bars import BarLog
from app.forward.runtime import ShadowRuntime
from tests.test_forward_deployments import repository,Registry,ACCOUNT
from tests.test_forward_bars import bar
from tests.test_incremental_engine import Signals


class RuntimeRegistry(Registry):
    def create(self,key,**params):return Signals(**params)

@pytest.fixture
def running(repository,monkeypatch):
    monkeypatch.setattr('app.forward.runtime.WARMUP_SESSIONS',1)
    registry=RuntimeRegistry()
    rows=repository.prepare('runtime',ACCOUNT,registry=registry);experiment=rows[0]['experiment_id']
    clock=[datetime(2026,1,2,14,30,tzinfo=timezone.utc)]
    log=BarLog(repository.database,lambda:clock[0])
    log.bind(experiment,provider='fixture',feed='raw',sessions=[
        dict(open='2025-12-31T14:30Z',close='2025-12-31T14:32Z'),
        dict(open='2026-01-02T14:30Z',close='2026-01-02T14:36Z')])
    log.append(experiment,[bar('2025-12-31T14:30:00+00:00'),bar('2025-12-31T14:31:00+00:00')])
    runtime=ShadowRuntime(repository.database,registry)
    runtime.bars=log
    runtime.activate(experiment)
    clock[0]=datetime(2026,1,2,14,40,tzinfo=timezone.utc)
    return runtime,experiment,registry

def minutes(n):return [bar(f'2026-01-02T14:{30+i}:00+00:00') for i in range(n)]

def test_all_four_independent_shadows_persist_once_and_recover(running):
    runtime,experiment,registry=running
    first=runtime.ingest(experiment,minutes(4))
    assert all(r['state']['status']=='ACTIVE' for r in first)
    assert len({id(v[1]) for v in runtime.instances.values()})==4
    assert all(len(v[1].calls)==4 for v in runtime.instances.values())
    assert runtime.ingest(experiment,minutes(4))==first
    restarted=ShadowRuntime(runtime.database,registry)
    restarted.bars=runtime.bars
    assert restarted.tick(experiment)==first
    final=restarted.ingest(experiment,minutes(6))
    assert all(r['state']['last_evaluated_decision_at']=='2026-01-02T14:36:00+00:00' for r in final)
    assert all(r['state']['position'] is None for r in final)
    with runtime.database.connect() as c:
        assert c.execute('SELECT count(*) FROM forward_checkpoints').fetchone()[0]==24

def test_source_change_halts_without_upgrade(running):
    runtime,experiment,registry=running
    runtime.ingest(experiment,minutes(2))
    registry.content['fixture.py']=b'# different\n'
    with pytest.raises(ValueError,match='changed'):runtime.tick(experiment)
    assert all(r['state']['status']=='HALTED' for r in runtime.deployments.list(experiment))

def test_native_completed_minute_contract_fills_next_open(running):
    runtime,experiment,_=running
    one=runtime.ingest(experiment,minutes(1))
    assert all(r['state']['position'] is None for r in one)
    two=runtime.ingest(experiment,minutes(2))
    assert all(r['state']['position']['entry_time']=='2026-01-02T14:31:00+00:00' for r in two)

def test_missing_minute_halts_and_keeps_last_good_checkpoints(running):
    runtime,experiment,_=running
    before=runtime.ingest(experiment,minutes(1))
    with pytest.raises(ValueError,match='Missing'):runtime.ingest(experiment,[minutes(3)[-1]])
    after=runtime.deployments.list(experiment)
    assert all(r['state']['status']=='HALTED' for r in after)
    assert [r['state']['last_evaluated_decision_at'] for r in after]==[r['state']['last_evaluated_decision_at'] for r in before]

def test_tampered_checkpoint_blocks_restart(running):
    runtime,experiment,registry=running
    runtime.ingest(experiment,minutes(2))
    with runtime.database.connect() as c:
        c.execute("UPDATE forward_checkpoints SET sha256='changed'")
    with pytest.raises(ValueError,match='diverged'):ShadowRuntime(runtime.database,registry).tick(experiment)
    assert all(r['state']['status']=='HALTED' for r in runtime.deployments.list(experiment))
