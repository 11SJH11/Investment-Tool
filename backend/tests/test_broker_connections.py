from copy import deepcopy
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest

from app.api.brokers import router
from app.brokers.base import BrokerHistoryError, HistoryBatch
from app.brokers.profiles import profiles
from app.brokers.trading212 import Trading212Portfolio
from app.core.config import Settings
from app.services.broker_connections import BrokerConnections
from app.storage.database import Database
from app.storage.journal_repository import JournalRepository
from app.storage.portfolio_repository import PortfolioRepository
from tests.test_oanda_journal_import import adapter as oanda_adapter, history


def settings(**kw):
    return Settings(_env_file=None, **kw)


class Provider:
    def __init__(self):
        self.calls = []
        self.account = 123456789
        self.positions = [{'instrument':{'ticker':'AAPL_US_EQ','currency':'USD'},'quantity':2,'averagePricePaid':100,
                           'currentPrice':110,'walletImpact':{'currency':'GBP','currentValue':176,'totalCost':160,'unrealizedProfitLoss':16}}]
        self.orders = [{'order':{'id':9,'side':'BUY','status':'FILLED','instrument':{'ticker':'AAPL_US_EQ','currency':'USD'}},
                        'fill':{'id':i,'quantity':1,'price':100,'filledAt':'2026-06-01T12:00:00Z','walletImpact':{'currency':'GBP','netValue':80}}} for i in (1,2)]
        self.failure = None
        self.next_page = None

    def handler(self, request):
        self.calls.append(request)
        assert request.method == 'GET'
        path = request.url.path
        if self.failure and path.endswith(self.failure):
            return httpx.Response(403,json={'message':'do not echo key-secret-private-account'})
        if path.endswith('/summary'):
            body={'id':self.account,'currency':'GBP','cash':{'availableToTrade':24},'investments':{'currentValue':176},'totalValue':200,'apiSecret':'do not persist'}
        elif path.endswith('/positions'): body=self.positions
        elif path.endswith('/orders'): body={'items':self.orders,'nextPagePath':self.next_page}
        elif path.endswith('/dividends'): body={'items':[{'reference':'div-1','amount':3,'currency':'GBP','ticker':'AAPL_US_EQ'}],'nextPagePath':None}
        else: body={'items':[{'reference':'cash-1','amount':50,'currency':'USD','type':'DEPOSIT'}],'nextPagePath':None}
        return httpx.Response(200,json=body)

    def factory(self,key,secret,environment):
        return Trading212Portfolio(key,secret,environment,client=httpx.Client(transport=httpx.MockTransport(self.handler)),sleep=lambda _:None)


@pytest.fixture
def setup(tmp_path):
    db=Database(tmp_path/'db');db.initialize();provider=Provider()
    config=settings(TRADING212_ENABLED=True,TRADING212_API_KEY='key-synthetic',TRADING212_API_SECRET='secret-synthetic')
    return db,provider,BrokerConnections(config,db,factories={'trading212':provider.factory})


@pytest.mark.parametrize('enabled,key,secret,environment',[(False,'k','s','demo'),(True,'','s','demo'),(True,'k','','live'),(True,' ','s','demo'),(True,'k','s','invalid')])
def test_incomplete_credentials_never_construct_adapter(tmp_path,enabled,key,secret,environment):
    service=BrokerConnections(settings(TRADING212_ENABLED=enabled,TRADING212_API_KEY=key,TRADING212_API_SECRET=secret,TRADING212_ENVIRONMENT=environment),Database(tmp_path/'db'),factories={'trading212':lambda *a:pytest.fail('remote construction')})
    assert service.status('trading212-default')['status']=='not_configured'
    assert service.sync('trading212-default')['status']=='not_configured'


def test_snapshots_history_dedup_notes_and_preservation(setup):
    db,p,s=setup
    manual=PortfolioRepository(db).add_transaction({'ticker':'MSFT','action':'BUY','quantity':1,'price':10,'occurred_at':'2026-01-01','note':'keep manual'})
    assert s.status('trading212-default')['status']=='never_synced' and not p.calls
    assert s.sync('trading212-default')['created']==5
    key=s.portfolio.accounts()[0]['account_key']
    rows=s.portfolio.records(key)['items'];row=next(r for r in rows if r['kind']=='position')
    s.portfolio.review(row['id'],'My note',['Long term'])
    p.positions[0]['quantity']=3
    assert s.sync('trading212-default')['created']==0
    again=next(r for r in s.portfolio.records(key)['items'] if r['id']==row['id'])
    assert again['note']=='My note' and again['tags']==['Long term'] and again['facts']['quantity']==3
    assert s.portfolio.records(key,'orders')['total']==2
    p.positions=[];s.sync('trading212-default')
    old=s.portfolio.records(key,'position')['items'][0]
    assert old['active']==0 and old['note']=='My note'
    assert PortfolioRepository(db).list_transactions()==[manual]
    assert JournalRepository(db).list_trades()==[]
    before=s.portfolio.records(key);db.initialize();db.initialize()
    assert s.portfolio.records(key)==before
    serialized=json.dumps([s.statuses(),s.portfolio.accounts(),before])
    assert str(p.account) not in serialized and 'secret-synthetic' not in serialized and 'do not persist' not in serialized
    assert all(r.headers['authorization'].startswith('Basic ') for r in p.calls)


def test_failed_history_preserves_all_facts_and_cursor(setup):
    db,p,s=setup;s.sync('trading212-default');key=s.portfolio.accounts()[0]['account_key']
    before=s.portfolio.records(key);cursor=s.state.state('trading212',key)['cursor']
    p.positions=[];p.failure='dividends'
    with pytest.raises(BrokerHistoryError,match='HTTP 403') as error:s.sync('trading212-default')
    assert 'key-secret' not in str(error.value)
    assert s.portfolio.records(key)==before and s.state.state('trading212',key)['cursor']==cursor


@pytest.mark.parametrize('next_path',['https://evil.example/api/v0/equity/history/orders','//evil.example/path','/api/v0/equity/orders','/api/v0/equity/history/orders?limit=50'])
def test_pagination_host_endpoint_and_loop_rejected(setup,next_path):
    _,p,s=setup;p.next_page=next_path
    with pytest.raises(BrokerHistoryError):s.sync('trading212-default')
    assert len(p.calls)==3 and s.portfolio.accounts()==[]


def test_pagination_followed_and_duplicate_fill_pages_deduplicated(setup):
    _,p,s=setup
    original=p.handler
    def handler(req):
        if req.url.params.get('cursor')=='2':
            p.calls.append(req);return httpx.Response(200,json={'items':p.orders,'nextPagePath':None})
        return original(req)
    p.handler=handler;p.next_page='/api/v0/equity/history/orders?limit=50&cursor=2'
    assert s.sync('trading212-default')['created']==5
    assert len(p.calls)==6


def test_accounts_environments_and_key_rotation_do_not_collide(setup):
    db,p,s=setup;s.sync('trading212-default')
    original=s.portfolio.accounts()[0]['account_key']
    p.account=998877;s.sync('trading212-default');assert len(s.portfolio.accounts())==2
    live=BrokerConnections(settings(TRADING212_ENABLED=True,TRADING212_API_KEY='other-key',TRADING212_API_SECRET='other-secret',TRADING212_ENVIRONMENT='live'),db,factories={'trading212':p.factory})
    live.sync('trading212-default');assert len(s.portfolio.accounts())==3
    assert any(r.url.host=='live.trading212.com' for r in p.calls)
    p.account=123456789;s.sync('trading212-default')
    assert s.portfolio.records(original)['total']==5


def test_multiple_oanda_profiles_retain_legacy_identity_review_and_partial_closes(tmp_path):
    db=Database(tmp_path/'db');db.initialize()
    def factory(token,account,env):
        a=oanda_adapter(account=account,environment=env)
        t,o,c,p=history();facts=a._map(t,o,c,p,'USD')
        a.fetch_closed=lambda cursor:HistoryBatch([deepcopy(facts)],'30')
        return a
    extra=[dict(id='second-practice',provider='oanda',environment='practice',credentials={'token':'synthetic','account_id':'other'}),dict(id='live-profile',provider='oanda',environment='live',credentials={'token':'synthetic','account_id':'same'})]
    s=BrokerConnections(settings(OANDA_ACCESS_TOKEN='synthetic',OANDA_ACCOUNT_ID='same',BROKER_PROFILES_JSON=json.dumps(extra)),db,factories={'oanda':factory})
    for id in ('oanda-default','second-practice','live-profile'):assert s.sync(id)['created']==1
    rows=JournalRepository(db).list_trades();assert len({r['external_id'] for r in rows})==3
    original=factory('synthetic','same','practice');t,o,c,p=history()
    assert original._map(t,o,c,p,'USD')['external_id'] in {r['external_id'] for r in rows};original.close()
    assert all(r['exit_price']==pytest.approx(1.126) for r in rows)
    for id in ('oanda-default','second-practice','live-profile'):assert s.sync(id)['created']==0
    assert all(s.status(id)['status']=='success' for id in ('oanda-default','second-practice','live-profile'))


@pytest.mark.parametrize('configured',[False,True])
def test_tradovate_never_constructs_remote_adapter(tmp_path,configured):
    s=BrokerConnections(settings(TRADOVATE_ENABLED=configured,TRADOVATE_CLIENT_ID='synthetic',TRADOVATE_CLIENT_SECRET='synthetic',TRADOVATE_ACCOUNT_ID='synthetic'),Database(tmp_path/'db'),factories={'tradovate':lambda *a:pytest.fail('network')})
    result=s.sync('tradovate-default')
    assert result['status']==('unsupported' if configured else 'not_configured')
    assert not result['supported'] and not result['execution']


@pytest.mark.parametrize('raw',['secret-not-json','{}','[{"id":"../x"}]','[{"id":"oanda-default","provider":"oanda","environment":"live"}]','[{"id":"bad","provider":"fake","environment":"live"}]'])
def test_bad_profile_configuration_is_sanitized(raw):
    with pytest.raises(BrokerHistoryError) as error:profiles(settings(BROKER_PROFILES_JSON=raw))
    assert raw not in str(error.value)


def test_broker_api_only_allows_review_mutations(setup):
    _,p,s=setup;app=FastAPI();app.state.services=SimpleNamespace(broker_connections=s);app.include_router(router,prefix='/api')
    with TestClient(app) as c:
        assert c.get('/api/brokers').status_code==200 and not p.calls
        assert c.post('/api/brokers/trading212-default/sync').status_code==200
        key=c.get('/api/portfolio/broker-accounts').json()['items'][0]['account_key']
        row=c.get('/api/portfolio/broker-records',params={'account_key':key}).json()['items'][0]
        url=f"/api/portfolio/broker-records/{row['id']}/review"
        assert c.patch(url,json={'note':'Keep','tags':['x']}).status_code==200
        assert c.patch(url,json={'facts':{'quantity':999}}).status_code==422
        assert c.post('/api/brokers/not-found/sync').status_code==400


def test_transport_exception_does_not_expose_credentials():
    def fail(req):raise RuntimeError('key-synthetic:secret-synthetic account-private')
    a=Trading212Portfolio('key-synthetic','secret-synthetic','demo',client=httpx.Client(transport=httpx.MockTransport(fail)))
    with pytest.raises(BrokerHistoryError) as error:a.read_account()
    assert 'synthetic' not in str(error.value) and 'account-private' not in str(error.value)
    a.close()


def test_rate_limit_retry_is_bounded_and_redirects_are_not_followed():
    calls=[];sleeps=[]
    def limited(req):
        calls.append(req);return httpx.Response(429,headers={'Retry-After':'1'})
    a=Trading212Portfolio('k','s','demo',client=httpx.Client(transport=httpx.MockTransport(limited)),sleep=sleeps.append)
    with pytest.raises(BrokerHistoryError,match='429'):a.read_account()
    assert len(calls)==1 and sleeps==[];a.close()
    calls.clear()
    def redirect(req):
        calls.append(req);return httpx.Response(302,headers={'Location':'https://evil.example'})
    a=Trading212Portfolio('k','s','demo',client=httpx.Client(transport=httpx.MockTransport(redirect)))
    with pytest.raises(BrokerHistoryError,match='302'):a.read_account()
    assert len(calls)==1;a.close()


def test_changed_credentials_do_not_show_previous_account_status(setup):
    db,p,s=setup;s.sync('trading212-default')
    rotated=BrokerConnections(settings(TRADING212_ENABLED=True,TRADING212_API_KEY='rotated',TRADING212_API_SECRET='rotated'),db,factories={'trading212':p.factory})
    assert rotated.status('trading212-default')['status']=='never_synced'
    assert rotated.sync('trading212-default')['created']==0
    assert len(rotated.portfolio.accounts())==1


def test_conflicting_page_records_roll_back_snapshot(setup):
    _,p,s=setup;s.sync('trading212-default');key=s.portfolio.accounts()[0]['account_key']
    old=s.portfolio.records(key);account=s.portfolio.accounts()
    duplicate=deepcopy(p.orders[0]);duplicate['fill']['price']=999;p.orders.append(duplicate)
    with pytest.raises(BrokerHistoryError):s.sync('trading212-default')
    assert s.portfolio.records(key)==old and s.portfolio.accounts()==account


def test_missing_quantity_cannot_replace_valid_holdings(setup):
    _,p,s=setup;s.sync('trading212-default');key=s.portfolio.accounts()[0]['account_key']
    before=s.portfolio.records(key);p.positions[0].pop('quantity')
    with pytest.raises(BrokerHistoryError,match='quantity'):s.sync('trading212-default')
    assert s.portfolio.records(key)==before


def test_stale_portfolio_cursor_cannot_overwrite_newer_sync(setup):
    _,p,s=setup
    a=p.factory('k','s','demo');summary=a.read_account();snap=a.fetch_snapshot(summary)
    s.portfolio.commit(a,snap,None)
    with pytest.raises(ValueError,match='Another sync'):s.portfolio.commit(a,snap,None)
    assert s.portfolio.records(a.account_key)['total']==5;a.close()
