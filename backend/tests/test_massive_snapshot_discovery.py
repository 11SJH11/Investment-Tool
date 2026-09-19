from datetime import date,datetime,timezone
from uuid import uuid4
import pytest
from app.data.massive_request_gate import MassiveRequestGate
from app.data.http import ProviderHttpError
from tests.test_massive_reference_cache import provider,CONTRACT


def test_point_in_time_snapshots_exclude_daily_directory_and_deduplicate(tmp_path):
    p=provider(tmp_path,lambda *a:{'results':[CONTRACT,CONTRACT]})
    assert len(p.list_contracts('NQ',as_of=date(2026,6,1)))==1
    assert p.http.calls[0]['params']=={'product_code':'NQ','date':'2026-06-01','type':'single','limit':1000}


def test_range_snapshots_reuse_metadata_across_intervals(tmp_path):
    p=provider(tmp_path,lambda *a:{'results':[CONTRACT]})
    start,end=datetime(2026,6,1,tzinfo=timezone.utc),datetime(2026,8,1,tzinfo=timezone.utc)
    assert len(p._range_contracts('NQ',start,end))==1
    first=len(p.http.calls);assert first<=3
    p._range_contracts('NQ',start,end);assert len(p.http.calls)==first


def test_shared_budget_and_cold_429_recovery():
    now=[0.];calls=[];sleeps=[]
    def sleep(seconds):sleeps.append(seconds);now[0]+=seconds
    class Http:
        def get_json(self,url,**kwargs):
            assert kwargs['max_attempts']==1
            calls.append(now[0])
            if len(calls)==1:raise ProviderHttpError('private',status_code=429,retry_after=75)
            return {'ok':True}
    key=str(uuid4());first=MassiveRequestGate(Http(),key,clock=lambda:now[0],sleep=sleep)
    second=MassiveRequestGate(Http(),key,clock=lambda:now[0],sleep=sleep)
    assert first.get_json('metadata')['ok'];assert second.get_json('bars')['ok']
    assert calls==[0,75,87.25]


def test_long_retry_after_does_not_block_or_leak_provider_message():
    class Http:
        def get_json(self,*a,**kw):raise ProviderHttpError('private-token',status_code=429,retry_after=600)
    gate=MassiveRequestGate(Http(),str(uuid4()),clock=lambda:0,sleep=lambda _:None)
    with pytest.raises(ProviderHttpError) as error:gate.get_json('metadata')
    assert error.value.retry_after==600 and 'private-token' not in str(error.value)
