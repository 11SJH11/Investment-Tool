from datetime import datetime,timezone
import httpx
import pytest
from app.forward.paper_client import PaperClient
from app.brokers.base import BrokerHistoryError

ORDER=dict(symbol='QQQ',qty='1',side='buy',type='market',time_in_force='day',extended_hours=False,client_order_id='fixture')

def test_paper_host_capability_and_no_redirect_or_retry():
    calls=[]
    def serve(request):
        calls.append(request)
        assert request.url.host=='paper-api.alpaca.markets'
        return httpx.Response(302,headers={'Location':'https://api.alpaca.markets/v2/orders'})
    client=PaperClient('paper-key','paper-secret',transport=httpx.MockTransport(serve))
    try:
        with pytest.raises(ValueError):client.submit(ORDER)
        approval=client.authorize(ORDER,datetime.now(timezone.utc).timestamp()+30)
        with pytest.raises(ValueError):client.submit({**ORDER,'qty':'100'},approval)
        with pytest.raises(BrokerHistoryError):client.submit(ORDER,approval)
        assert len(calls)==1
    finally:client.close()

def test_timeout_is_unknown_and_next_operation_is_explicit_client_id_lookup():
    calls=[]
    def serve(request):
        calls.append(request)
        if request.method=='POST':raise httpx.ReadTimeout('paper-secret',request=request)
        assert request.url.path=='/v2/orders:by_client_order_id'
        return httpx.Response(200,json={'id':'broker-order','client_order_id':'fixture','status':'accepted'})
    client=PaperClient('paper-key','paper-secret',transport=httpx.MockTransport(serve))
    try:
        approval=client.authorize(ORDER,datetime.now(timezone.utc).timestamp()+30)
        with pytest.raises(BrokerHistoryError) as error:client.submit(ORDER,approval)
        assert 'paper-secret' not in str(error.value)
        assert len(calls)==1 and client.find('fixture')['status']=='accepted'
        assert [r.method for r in calls]==['POST','GET']
    finally:client.close()

def test_missing_order_is_not_a_fill_and_rate_limit_is_exposed_safely():
    responses=iter([httpx.Response(404),httpx.Response(429,headers={'Retry-After':'45'},text='secret')])
    client=PaperClient('key','secret',transport=httpx.MockTransport(lambda _:next(responses)))
    try:
        assert client.find('missing') is None
        with pytest.raises(BrokerHistoryError) as error:client.account()
        assert error.value.retry_after==45 and error.value.category=='rate_limit'
        assert 'secret' not in str(error.value)
    finally:client.close()
