from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event

import httpx
import pytest

from app.data.contract_reference_cache import ContractReferenceCache
from app.data.http import JsonHttpClient, ProviderHttpError, _retry_delay
from app.data.providers.massive_futures import MassiveFuturesProvider
from tests.fakes import FakeJsonHttpClient

CONTRACT = dict(ticker="NQU6", product_code="NQ", type="single", first_trade_date="2025-01-01", last_trade_date="2026-09-18")


def provider(tmp_path, handler):
    return MassiveFuturesProvider("synthetic", http=FakeJsonHttpClient(handler), reference_cache_path=tmp_path/"reference.sqlite")


def test_reference_is_durable_separate_and_reused_across_timeframes(tmp_path):
    def handler(url, params, headers):
        if url.endswith("/contracts"):
            return {"results":[CONTRACT]}
        return {"results":[dict(window_start=1780300800000000000,open=25000,high=25001,low=24999,close=25000,volume=10)]}
    p=provider(tmp_path,handler)
    for tf in ("1m","5m","15m","1h","1m"):
        bars=p.get_bars("NQ1!",tf,datetime(2026,6,1,tzinfo=timezone.utc),datetime(2026,6,2,tzinfo=timezone.utc))
        assert bars.source_contract.tolist()==["NQU6"]
    assert sum(c["url"].endswith("/contracts") for c in p.http.calls)==1
    other=provider(tmp_path,lambda *a:pytest.fail("cached metadata should survive a new provider instance"))
    assert other.list_contracts("NQ")[0].ticker=="NQU6"
    assert (tmp_path/"reference.sqlite").exists()


def test_concurrent_discovery_is_single_flight_across_provider_instances(tmp_path):
    started,finish=Event(),Event()
    calls=[]
    def handler(*args):
        calls.append(1);started.set();assert finish.wait(5)
        return {"results":[CONTRACT]}
    first,second=provider(tmp_path,handler),provider(tmp_path,handler)
    with ThreadPoolExecutor(max_workers=6) as pool:
        tasks=[pool.submit(p.list_contracts,"NQ") for p in (first,second,first,second,first,second)]
        assert started.wait(5);finish.set()
        assert all(t.result()[0].ticker=="NQU6" for t in tasks)
    assert len(calls)==1


def test_ttl_and_explicit_refresh(tmp_path):
    calls=[]
    p=provider(tmp_path,lambda *a:(calls.append(1) or {"results":[CONTRACT]}))
    now=[100000.];p.reference_cache.clock=lambda:now[0]
    p.list_contracts("NQ");now[0]+=60;p.list_contracts("NQ")
    assert len(calls)==1
    p.list_contracts("NQ",refresh=True);assert len(calls)==2
    now[0]+=86401;p.list_contracts("NQ");assert len(calls)==3


def test_market_service_refresh_updates_reference_once_and_preserves_cached_provenance(tmp_path):
    from app.services.market_data import MarketDataService
    from app.storage.database import Database
    from app.storage.market_cache_repository import MarketCacheRepository
    from app.storage.market_store import MarketStore
    def handler(url,params,headers):
        if url.endswith('/contracts'):return {'results':[CONTRACT]}
        return {'results':[dict(window_start=1780300800000000000,open=25000,high=25001,low=24999,close=25000,volume=10)]}
    p=provider(tmp_path,handler);db=Database(tmp_path/'app.sqlite');db.initialize()
    service=MarketDataService(p,MarketStore(tmp_path/'ohlcv'),MarketCacheRepository(db))
    start,end=datetime(2026,6,1,tzinfo=timezone.utc),datetime(2026,6,2,tzinfo=timezone.utc)
    for refresh in (False,False,True,False):
        frame=service.get_bars('NQ1!','1m',start,end,force_refresh=refresh)
        assert frame.source_contract.tolist()==['NQU6']
    assert sum(c['url'].endswith('/contracts') for c in p.http.calls)==2
    assert sum('/aggs/' in c['url'] for c in p.http.calls)==2


def test_safe_stale_cache_on_429_and_persisted_cooldown(tmp_path):
    calls=[];limited=[False]
    def handler(*args):
        calls.append(1)
        if limited[0]: raise ProviderHttpError("HTTP 429 synthetic",status_code=429,retry_after=120)
        return {"results":[CONTRACT]}
    p=provider(tmp_path,handler);now=[100000.];p.reference_cache.clock=lambda:now[0]
    expected=p.list_contracts("NQ");limited[0]=True;now[0]+=86401
    assert p.list_contracts("NQ")==expected
    again=provider(tmp_path,lambda *a:pytest.fail("retry cooldown must persist"));again.reference_cache.clock=lambda:now[0]
    assert again.list_contracts("NQ",refresh=True)==expected
    assert len(calls)==2
    now[0]+=30*86400
    with pytest.raises(ProviderHttpError,match="no usable cached"):
        p.list_contracts("NQ")


def test_no_cache_429_clear_error_and_no_repeated_discovery(tmp_path):
    calls=[]
    def limited(*args):
        calls.append(1);raise ProviderHttpError("HTTP 429 credential-value",status_code=429)
    p=provider(tmp_path,limited)
    for _ in range(3):
        with pytest.raises(ProviderHttpError,match="rate-limited") as error:
            p.list_contracts("NQ")
        assert "credential-value" not in str(error.value)
    assert len(calls)==1


@pytest.mark.parametrize("next_url",["https://evil.test/futures/v1/contracts?cursor=x",
    "/futures/v1/aggs/NQU6", "/futures/v1/contracts", "/futures/v1/contracts#fragment"])
def test_contract_pagination_rejects_wrong_host_endpoint_loop_and_fragment(tmp_path,next_url):
    p=provider(tmp_path,lambda *a:{"results":[CONTRACT],"next_url":next_url})
    with pytest.raises(ValueError,match="pagination"):
        p.list_contracts("NQ")
    assert len(p.http.calls)==1


def test_contract_pagination_follows_cursor_and_preserves_fields(tmp_path):
    second={**CONTRACT,"ticker":"NQZ6","last_trade_date":"2026-12-18"}
    p=provider(tmp_path,lambda url,*a: {"results":[second]} if "cursor=2" in url else
        {"results":[CONTRACT],"next_url":"/futures/v1/contracts?cursor=2"})
    assert [c.ticker for c in p.list_contracts("NQ")]==["NQU6","NQZ6"]
    assert len(p.http.calls)==2 and p.http.calls[1]["params"]=={}


def test_corrupt_response_is_not_cached(tmp_path):
    p=provider(tmp_path,lambda *a:{"error":"invalid"})
    with pytest.raises(ValueError,match="incomplete"):
        p.list_contracts("NQ")
    p.http=FakeJsonHttpClient(lambda *a:{"results":[CONTRACT]})
    assert p.list_contracts("NQ")[0].ticker=="NQU6"


@pytest.mark.parametrize("delay,expected_calls",[("1",3),("120",1)])
def test_http_retry_is_bounded_and_does_not_retry_before_long_retry_after(monkeypatch,delay,expected_calls):
    calls=[];sleeps=[]
    def limited(request):
        calls.append(request);return httpx.Response(429,headers={"Retry-After":delay},json={"message":"rate limited"})
    client=JsonHttpClient();client._client.close();client._client=httpx.Client(transport=httpx.MockTransport(limited))
    monkeypatch.setattr("app.data.http.time.sleep",sleeps.append)
    try:
        with pytest.raises(ProviderHttpError) as error: client.get_json("https://api.massive.com/futures/v1/contracts")
        assert error.value.status_code==429 and error.value.retry_after==int(delay)
        assert len(calls)==expected_calls
        assert sleeps==([1,1] if delay=="1" else [])
    finally: client.close()


def test_http_date_retry_after_is_supported():
    response=httpx.Response(429,headers={"Retry-After":"Tue, 01 Jan 2030 00:00:00 GMT"})
    assert _retry_delay(response,1)>30


@pytest.mark.parametrize('value',['NaN','Infinity','not-a-date'])
def test_invalid_retry_after_uses_finite_backoff(value):
    assert _retry_delay(httpx.Response(429,headers={'Retry-After':value}),1)==.25
