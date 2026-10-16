import httpx
import pytest
from app.forward.alpaca_data import AlpacaForwardData
from app.brokers.base import BrokerHistoryError

def test_calendar_dst_and_early_close_are_provider_facts():
    def serve(request):
        assert str(request.url).startswith('https://paper-api.alpaca.markets/v2/calendar')
        return httpx.Response(200,json=[{'date':'2026-03-06','open':'09:30','close':'16:00'},
                                        {'date':'2026-03-09','open':'09:30','close':'13:00'}])
    with_provider=AlpacaForwardData('key','secret',transport=httpx.MockTransport(serve))
    try:
        values=with_provider.calendar('2026-03-06','2026-03-09')
        assert values[0]['open']=='2026-03-06T14:30:00+00:00'
        assert values[1]['open']=='2026-03-09T13:30:00+00:00'
        assert values[1]['close']=='2026-03-09T17:00:00+00:00'
    finally:with_provider.close()

def test_bars_pin_iex_raw_paginate_and_exclude_incomplete():
    requests=[]
    def serve(request):
        requests.append(request)
        assert request.method=='GET' and request.url.host=='data.alpaca.markets'
        assert request.url.params['feed']=='iex' and request.url.params['adjustment']=='raw'
        second=len(requests)==2
        return httpx.Response(200,json={'bars':[{'t':'2026-01-02T14:31:00Z' if second else '2026-01-02T14:30:00Z',
            'o':100,'h':101,'l':99,'c':100,'v':3}], 'next_page_token':None if second else 'page2'})
    provider=AlpacaForwardData('key','secret',transport=httpx.MockTransport(serve))
    try:
        bars=provider.bars('2026-01-02T14:30Z','2026-01-02T14:31:30Z')
        assert len(bars)==1 and len(requests)==2
    finally:provider.close()

@pytest.mark.parametrize('status',[302,401,403,429,500])
def test_errors_never_follow_redirects_or_expose_credentials(status):
    calls=[]
    def serve(request):
        calls.append(request)
        return httpx.Response(status,headers={'Location':'https://evil.invalid','Retry-After':'60'},text='key-secret provider body')
    provider=AlpacaForwardData('key-secret','password-secret',transport=httpx.MockTransport(serve))
    try:
        with pytest.raises(BrokerHistoryError) as error:provider.calendar('2026-01-01','2026-01-02')
        assert 'secret' not in str(error.value) and len(calls)==1
        if status==429:assert error.value.retry_after==60
    finally:provider.close()
