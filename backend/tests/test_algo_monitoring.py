import json
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from app.storage.database import Database
from app.services.algo_monitoring import report


@pytest.fixture
def services(tmp_path):
    db=Database(tmp_path/'monitor.db');db.initialize()
    return SimpleNamespace(database=db)


def test_empty_monitor_does_not_create_execution_state(services):
    with services.database.connect() as c:
        before=c.execute("SELECT name FROM sqlite_master ORDER BY name").fetchall()
    result=report(services)
    assert result['items']==[] and result['broker_totals'] is None
    assert not result['mt5_execution_enabled']
    with services.database.connect() as c:
        assert c.execute("SELECT name FROM sqlite_master ORDER BY name").fetchall()==before


def test_policy_never_becomes_running_or_attributes_manual_trades(services):
    policy=dict(account_key='a'*64,environment='demo',currency='USD',strategy_key='t01',strategy_source_hash='b'*64,symbols=['XAUUSD'])
    document=dict(id='policy',policy=policy,status='DISABLED',enabled=True)
    with services.database.connect() as c:
        c.execute('CREATE TABLE mt5_execution_policies(document TEXT)')
        c.execute('INSERT INTO mt5_execution_policies VALUES(?)',(json.dumps(document),))
    services.broker_connections=SimpleNamespace(statuses=lambda:dict(items=[dict(provider='mt5',profile_id='demo',environment='demo',status='synced',account_key='a'*64,credentials='DO_NOT_EXPOSE')]))
    result=report(services);row=result['items'][0]
    assert row['status']=='NOT_DEPLOYED' and row['trades']==[] and row['metrics'] is None
    assert not row['execution_enabled'] and 'DO_NOT_EXPOSE' not in json.dumps(result)
    with services.database.connect() as c:
        assert json.loads(c.execute('SELECT document FROM mt5_execution_policies').fetchone()[0])==document


@pytest.mark.parametrize('alive,status',[(False,'WORKER_UNAVAILABLE'),(True,'AWAITING_FRESH_EVALUATION')])
def test_shadow_state_is_not_broker_performance_or_proof_of_worker_health(services,alive,status):
    deployment=dict(id='shadow',name='Shadow',definition_sha256='hash',definition=dict(strategy_key='vwap',symbol='QQQ',engine={}),
        state=dict(status='ACTIVE',equity=10001,trade_history=[{'net_pnl':1}]*110),metrics={'n':110})
    services.forward=SimpleNamespace(thread=SimpleNamespace(is_alive=lambda:alive),report=lambda:dict(items=[dict(deployments=[deployment])]))
    result=report(services);row=result['items'][0]
    assert row['status']==status and row['mode']=='SHADOW' and row['environment']=='simulation'
    assert len(row['trades'])==100 and len(deployment['state']['trade_history'])==110
    assert result['broker_totals'] is None and row['account_key'] is None


def test_monitor_endpoint_has_no_execution_actions(services):
    from app.api.algo_trading import router
    app=FastAPI();app.include_router(router);app.state.services=services
    with TestClient(app) as client:
        assert client.get('/algo-trading').status_code==200
        assert client.post('/algo-trading').status_code==405
        assert client.post('/algo-trading/start').status_code==404


def test_recovery_projection_is_bounded_readonly_and_not_trading_authority(services):
    with services.database.connect() as c:
        c.execute('CREATE TABLE mt5_execution_intents(id TEXT,policy_id TEXT)')
        c.execute('CREATE TABLE mt5_execution_reconciliations(id TEXT,intent_id TEXT,document TEXT)')
        c.execute('INSERT INTO mt5_execution_intents VALUES(?,?)',('intent','policy'))
        for i in range(105):
            record=dict(id=str(i),intent_id='intent',observed_at_ms=1000+i,complete=True,
                identity_basis='durable_attempt_receipt',execution_enabled=True,attribution_verified=True,
                secret='DO_NOT_EXPOSE',decision=dict(state='FILLED_PROTECTED',filled_lots='0.1',remaining_lots='0.1'))
            c.execute('INSERT INTO mt5_execution_reconciliations VALUES(?,?,?)',(str(i),'intent',json.dumps(record)))
    result=report(services)
    assert len(result['recovery_observations'])==100
    row=result['recovery_observations'][0]
    assert row['id']=='104' and row['policy_id']=='policy' and row['state']=='FILLED_PROTECTED'
    assert not row['execution_enabled'] and not row['attribution_verified']
    assert 'DO_NOT_EXPOSE' not in json.dumps(result)
    assert result['items']==[] and result['broker_totals'] is None
    with services.database.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM mt5_execution_reconciliations').fetchone()[0]==105


def test_recovery_filter_precedes_page_limit_and_cursor_survives_new_events(services):
    from app.services.algo_monitoring import recovery_page
    test_recovery_projection_is_bounded_readonly_and_not_trading_authority(services)
    with services.database.connect() as c:
        c.execute('INSERT INTO mt5_execution_intents VALUES(?,?)',('quiet-intent','quiet-policy'))
        c.execute("UPDATE mt5_execution_reconciliations SET intent_id='quiet-intent' WHERE id='0'")
    quiet=recovery_page(services.database,policy_id='quiet-policy')
    assert [r['id'] for r in quiet['items']]==['0'] and quiet['next_before'] is None
    first=recovery_page(services.database,policy_id='policy',limit=3)
    assert [r['id'] for r in first['items']]==['104','103','102']
    with services.database.connect() as c:
        record=dict(id='new',intent_id='intent',decision={'state':'UNRESOLVED'})
        c.execute('INSERT INTO mt5_execution_reconciliations VALUES(?,?,?)',('new','intent',json.dumps(record)))
    second=recovery_page(services.database,policy_id='policy',before=first['next_before'],limit=3)
    assert [r['id'] for r in second['items']]==['101','100','99']
    assert recovery_page(services.database,policy_id='unknown')['items']==[]


def test_recovery_endpoint_validates_cursor_and_bounds(services):
    from app.api.algo_trading import router
    app=FastAPI();app.include_router(router);app.state.services=services
    with TestClient(app) as client:
        assert client.get('/algo-trading/recovery').json()=={'items':[],'next_before':None}
        for query in ('limit=0','limit=101','before=0','before=-1','policy_id='):
            assert client.get('/algo-trading/recovery?'+query).status_code==422
        assert client.post('/algo-trading/recovery').status_code==405
