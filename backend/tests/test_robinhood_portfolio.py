"""Synthetic contracts: live Robinhood schemas still require opt-in acceptance."""
from copy import deepcopy
import json
import httpx
import pytest
from app.brokers.base import BrokerHistoryError
from app.brokers.robinhood import RobinhoodMCP, RobinhoodPortfolio
from app.brokers.execution_provider import ReadOnlyExecutionDestination
from app.core.config import Settings
from app.services.broker_connections import BrokerConnections
from app.storage.database import Database

class Transport:
    def __init__(self):
        self.tools={name:{'inputSchema':{'properties':{'account_id':{},'cursor':{}},'required':['account_id']}} for name in ('get_portfolio','get_equity_positions','get_option_positions','get_crypto_positions','place_equity_order')}
        self.tools['get_accounts']={'inputSchema':{}}
        self.account='synthetic-account';self.bad=False;self.wrong=False;self.calls=[]
    def discover(self):return self.tools
    def close(self):pass
    def call(self,name,args):
        self.calls.append((name,deepcopy(args)))
        assert not name.startswith('place_')
        if self.bad:raise BrokerHistoryError('Unavailable',category='provider')
        if name=='get_accounts':return {'accounts':[{'id':self.account,'currency':'USD','account_type':'individual'}]}
        assert args['account_id']==self.account
        if name=='get_portfolio':return {'total_value':220,'cash':20,'currency':'USD'}
        if name=='get_equity_positions':return {'positions':[{'id':'holding-1','symbol':'AAPL','quantity':'2','market_value':'200','cost_basis':'180','unrealized_pnl':'20','account_id':'wrong' if self.wrong else self.account}]}
        return {'positions':[]}

@pytest.fixture
def setup(tmp_path):
    db=Database(tmp_path/'db');db.initialize();transport=Transport()
    settings=Settings(_env_file=None,ROBINHOOD_ENABLED=True,ROBINHOOD_PORTFOLIO_SYNC=True,ROBINHOOD_ACCESS_TOKEN='synthetic-secret')
    service=BrokerConnections(settings,db,factories={'robinhood':lambda c,e:RobinhoodPortfolio(c,e,transport=transport)})
    return db,transport,service

def test_sync_normalization_dedup_notes_and_capabilities(setup):
    db,t,s=setup
    assert s.status('robinhood-default')['status']=='never_synced' and not t.calls
    assert s.sync('robinhood-default')['created']==1
    account=s.portfolio.accounts()[0];key=account['account_key']
    assert account['provider']=='robinhood' and account['summary']['totalValue']==220
    row=s.portfolio.records(key)['items'][0]
    assert row['facts']['quantity']==2 and row['facts']['walletImpact']['unrealizedProfitLoss']==20
    s.portfolio.review(row['id'],'keep',['long term'])
    assert s.sync('robinhood-default')['created']==0
    assert s.portfolio.records(key)['items'][0]['note']=='keep'
    status=s.status('robinhood-default');assert status['discovered_capabilities']['provider_equities_execution']
    assert not status['execution'] and not status['discovered_capabilities']['ledger_execution']
    assert 'synthetic-secret' not in json.dumps([status,account,row])
    assert 'synthetic-account' not in json.dumps([status,account,row])

@pytest.mark.parametrize('failure',['bad','wrong','permission'])
def test_failure_keeps_last_good_snapshot(setup,failure):
    _,t,s=setup;s.sync('robinhood-default');key=s.portfolio.accounts()[0]['account_key'];before=s.portfolio.records(key)
    if failure=='permission':t.tools.pop('get_option_positions')
    else:setattr(t,failure,True)
    with pytest.raises(BrokerHistoryError):s.sync('robinhood-default')
    assert s.portfolio.records(key)==before

def test_separate_accounts_and_identity(setup):
    _,t,s=setup;s.sync('robinhood-default');first=s.portfolio.accounts()[0]['account_key']
    t.account='second-account';s.sync('robinhood-default')
    assert len(s.portfolio.accounts())==2
    assert s.portfolio.records(first)['total']==1

def test_execution_disabled_for_every_instrument():
    provider=ReadOnlyExecutionDestination('robinhood')
    assert not provider.capabilities().enabled and not provider.capabilities().futures
    with pytest.raises(BrokerHistoryError):provider.submit({'symbol':'NQ'},risk_approval=True)

@pytest.mark.parametrize('status',[401,403,429,302])
def test_transport_auth_backoff_and_no_secret_leak(status):
    calls=[]
    def handler(req):
        calls.append(req);return httpx.Response(status,json={'private':'synthetic-secret'},headers={'Retry-After':'13','Location':'https://example.com'})
    client=RobinhoodMCP('synthetic-secret',httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(BrokerHistoryError) as exc:client.discover()
    assert len(calls)==1 and 'synthetic-secret' not in str(exc.value)
    if status==429:assert str(exc.value.retry_after)=='13'
    client.close()

def test_tool_allowlist_before_network():
    client=RobinhoodMCP('synthetic',httpx.Client(transport=httpx.MockTransport(lambda _:pytest.fail('network'))))
    with pytest.raises(BrokerHistoryError,match='read-only'):client.call('place_equity_order',{})
    client.close()


def test_official_mcp_protocol_and_structured_read_contract():
    fixture=Transport();calls=[]
    def handler(req):
        body=json.loads(req.content);calls.append(body);method=body['method']
        if method=='notifications/initialized':return httpx.Response(202)
        if method=='initialize':result={'protocolVersion':'2025-03-26'}
        elif method=='tools/list':result={'tools':[{'name':name,**schema} for name,schema in fixture.tools.items()]}
        else:
            assert method=='tools/call'
            result={'structuredContent':fixture.call(body['params']['name'],body['params']['arguments'])}
        return httpx.Response(200,json={'jsonrpc':'2.0','id':body['id'],'result':result},headers={'Mcp-Session-Id':'fixture-session'})
    transport=RobinhoodMCP('fixture-token',httpx.Client(transport=httpx.MockTransport(handler)))
    adapter=RobinhoodPortfolio({},transport=transport)
    account=adapter.read_account();snapshot=adapter.fetch_snapshot(account)
    assert len(snapshot.positions)==1 and snapshot.summary['totalValue']==220
    assert [c['method'] for c in calls[:3]]==['initialize','notifications/initialized','tools/list']
    adapter.close();assert not transport.headers

def test_trading212_and_robinhood_coexist_without_merging_accounts(tmp_path):
    from tests.test_broker_connections import Provider
    db=Database(tmp_path/'db');db.initialize();t212=Provider();rh=Transport()
    config=Settings(_env_file=None,TRADING212_ENABLED=True,TRADING212_API_KEY='fixture',TRADING212_API_SECRET='fixture',ROBINHOOD_ENABLED=True,ROBINHOOD_PORTFOLIO_SYNC=True,ROBINHOOD_ACCESS_TOKEN='fixture')
    service=BrokerConnections(config,db,factories={'trading212':t212.factory,'robinhood':lambda c,e:RobinhoodPortfolio(c,e,transport=rh)})
    service.sync('trading212-default');service.sync('robinhood-default')
    accounts=service.portfolio.accounts();assert len(accounts)==2 and len({a['account_key'] for a in accounts})==2
    assert {a['provider'] for a in accounts}=={'trading212','robinhood'}
    for a in accounts:
        rows=service.portfolio.records(a['account_key'])['items']
        assert rows and all(r['provider']==a['provider'] for r in rows)
