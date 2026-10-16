from datetime import datetime, timedelta, timezone
import pytest
from app.forward.bars import BarLog
from tests.test_forward_deployments import repository, Registry, ACCOUNT

def bar(at,**changes):
    start=datetime.fromisoformat(at)
    return dict(timestamp=at,available_at=(start+timedelta(minutes=1)).isoformat(),
                open=100,high=101,low=99,close=100,volume=20,**changes)

@pytest.fixture
def log(repository):
    experiment=repository.prepare('fixture',ACCOUNT,registry=Registry())[0]['experiment_id']
    clock=[datetime(2026,3,6,14,30,tzinfo=timezone.utc)]
    store=BarLog(repository.database,lambda:clock[0])
    sessions=[dict(open='2026-03-06T14:30:00+00:00',close='2026-03-06T14:32:00+00:00'),
              dict(open='2026-03-09T13:30:00+00:00',close='2026-03-09T13:32:00+00:00')]
    store.bind(experiment,provider='fixture',feed='raw',sessions=sessions)
    clock[0]=datetime(2026,3,10,tzinfo=timezone.utc)
    return store,experiment,clock

def test_completed_bars_survive_restart_and_duplicate_delivery(log):
    store,experiment,clock=log
    bars=[bar('2026-03-06T14:30:00+00:00'),bar('2026-03-06T14:31:00+00:00')]
    assert store.append(experiment,bars)==2
    assert BarLog(store.database,lambda:clock[0]).append(experiment,bars)==0
    assert len(store.read(experiment)[1])==2

def test_weekend_dst_and_short_session_follow_explicit_provider_calendar(log):
    store,experiment,_=log
    bars=[bar(t) for t in ['2026-03-06T14:30:00+00:00','2026-03-06T14:31:00+00:00',
                           '2026-03-09T13:30:00+00:00','2026-03-09T13:31:00+00:00']]
    assert store.append(experiment,bars)==4

@pytest.mark.parametrize('fault',['future','naive','range','volume','missing','changed','order','outside'])
def test_invalid_data_never_partially_commits(log,fault):
    store,experiment,clock=log
    original=bar('2026-03-06T14:30:00+00:00')
    store.append(experiment,[original]);bad=bar('2026-03-06T14:31:00+00:00')
    if fault=='future':clock[0]=datetime(2026,3,6,14,31,tzinfo=timezone.utc)
    elif fault=='naive':bad['timestamp']='2026-03-06T14:31:00'
    elif fault=='range':bad['high']=90
    elif fault=='volume':bad['volume']=-1
    elif fault=='missing':bad=bar('2026-03-09T13:30:00+00:00')
    elif fault=='changed':bad={**original,'volume':99}
    elif fault=='outside':bad=bar('2026-03-06T18:00:00+00:00')
    values=[bad,original] if fault=='order' else [bad]
    with pytest.raises(ValueError):store.append(experiment,values)
    assert len(store.read(experiment)[1])==1

def test_feed_identity_cannot_change(log):
    store,experiment,_=log
    with pytest.raises(ValueError,match='immutable'):
        store.bind(experiment,provider='other',feed='raw',sessions=[dict(open='2026-03-06T14:30Z',close='2026-03-06T21:00Z')])
