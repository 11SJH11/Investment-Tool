import json
from types import SimpleNamespace as NS

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.brokers import router
from app.api.dependencies import get_services
from app.brokers.base import BrokerHistoryError
from app.brokers.metatrader5 import MetaTrader5History
from app.core.config import Settings
from app.services.broker_connections import BrokerConnections
from app.storage.database import Database


class Terminal:
    SYMBOL_CALC_MODE_CFDINDEX = 3
    def __init__(self):
        self.login = 123
        self.mode = 0
        self.calls = []
        self.rows = [NS(name='NASUSD', description='Broker Nasdaq CFD', path='Indices',
                        trade_calc_mode=3, trade_tick_size=.1, trade_tick_value=.1,
                        trade_contract_size=1, volume_step=.01, currency_profit='USD',
                        password='not-a-public-field'), NS(name='NQ1!')]
    def initialize(self, **kwargs):
        self.calls.append('initialize')
        return True
    def shutdown(self):
        self.calls.append('shutdown')
    def account_info(self):
        return NS(login=self.login, server='fixture', currency='USD', trade_mode=self.mode)
    def symbols_get(self):
        self.calls.append('symbols_get')
        return self.rows


@pytest.fixture
def setup(tmp_path):
    db = Database(tmp_path / 'catalog.db')
    db.initialize()
    terminal = Terminal()
    settings = Settings(_env_file=None, MT5_ENABLED=True)
    service = BrokerConnections(settings, db, factories={
        'mt5': lambda credentials, environment: MetaTrader5History(credentials, environment, module=terminal)})
    account = service.discover('mt5-default')['items'][0]['account_key']
    service.select_account('mt5-default', account)
    return service, terminal, db


def test_catalog_keeps_broker_identity_metadata_and_unknowns(setup):
    service, terminal, db = setup
    result = service.symbol_catalog('mt5-default', refresh=True)
    cfd, unknown = result['items']
    assert cfd['instrument_type'] == 'cfd'
    assert cfd['trade_tick_size'] == .1 and cfd['trade_contract_size'] == 1
    assert cfd['canonical_symbol'] is None and not cfd['futures_verified']
    assert unknown['instrument_type'] == 'unknown' and unknown['trade_tick_size'] is None
    assert unknown['trading_sessions'] is None
    assert 'not-a-public-field' not in json.dumps(result)
    assert len(result['account_key']) == 64
    assert 'login' not in result and 'server' not in result
    assert terminal.calls[-1] == 'shutdown'
    before = list(terminal.calls)
    cached = service.symbol_catalog('mt5-default', search='nasdaq', limit=1)
    assert cached['total'] == 1 and cached['catalog_total'] == 2
    assert terminal.calls == before
    assert cached['fingerprint'] == result['fingerprint']


@pytest.mark.parametrize('failure', ['none', 'exception', 'duplicate', 'account_changed'])
def test_failure_preserves_catalog_and_releases_terminal_lock(setup, failure):
    service, terminal, db = setup
    initial = service.symbol_catalog('mt5-default', refresh=True)
    original = terminal.symbols_get
    def bad():
        if failure == 'exception':
            raise RuntimeError('secret native diagnostic')
        if failure == 'none':
            return None
        if failure == 'duplicate':
            return terminal.rows * 2
        terminal.login = 456
        return terminal.rows
    terminal.symbols_get = bad
    with pytest.raises(BrokerHistoryError) as error:
        service.symbol_catalog('mt5-default', refresh=True)
    assert 'secret native' not in str(error.value)
    assert service.symbol_catalog('mt5-default')['fingerprint'] == initial['fingerprint']
    terminal.login = 123
    terminal.symbols_get = original
    assert service.symbol_catalog('mt5-default', refresh=True)['fingerprint'] == initial['fingerprint']


def test_accounts_and_environments_are_distinct(setup):
    service, terminal, db = setup
    original = service.symbol_catalog('mt5-default', refresh=True)['items'][0]['instrument_id']
    terminal.login = 456
    key = service.discover('mt5-default')['items'][0]['account_key']
    service.select_account('mt5-default', key)
    assert service.symbol_catalog('mt5-default')['status'] == 'not_discovered'
    other = service.symbol_catalog('mt5-default', refresh=True)['items'][0]['instrument_id']
    service.configure_connection('mt5-default', True, 'live')
    terminal.mode = 2
    key = service.discover('mt5-default')['items'][0]['account_key']
    service.select_account('mt5-default', key)
    live = service.symbol_catalog('mt5-default', refresh=True)['items'][0]['instrument_id']
    assert len({original, other, live}) == 3


def test_api_paging_and_disabled_refresh(setup):
    service, terminal, db = setup
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_services] = lambda: NS(broker_connections=service)
    with TestClient(app) as client:
        assert client.post('/brokers/mt5-default/symbols/refresh').status_code == 200
        assert client.get('/brokers/mt5-default/symbols?limit=1&offset=1').json()['items'][0]['name'] == 'NQ1!'
        assert client.get('/brokers/mt5-default/symbols?limit=501').status_code == 422
        service.configure_connection('mt5-default', False, 'demo')
        before = list(terminal.calls)
        assert client.post('/brokers/mt5-default/symbols/refresh').status_code == 400
        assert terminal.calls == before


def test_selection_required_and_profile_lock_respected(setup):
    service, terminal, db = setup
    lock = service._profile_locks['mt5-default']
    lock.acquire()
    try:
        with pytest.raises(BrokerHistoryError, match='already running'):
            service.symbol_catalog('mt5-default', refresh=True)
    finally:
        lock.release()
    service.configure_connection('mt5-default', True, 'live')
    with pytest.raises(BrokerHistoryError, match='select an account'):
        service.symbol_catalog('mt5-default', refresh=True)
