from types import SimpleNamespace as NS

import duckdb
import pandas as pd
import pytest

from app.brokers.base import BrokerHistoryError
from app.data.mt5_history import history_request
from tests.test_mt5_symbol_catalog import setup  # isolated database/account fixture


def wire(terminal):
    terminal.TIMEFRAME_M1 = 1
    terminal.COPY_TICKS_ALL = 0
    terminal.symbol_info = lambda name: NS(name=name, trade_calc_mode=3, point=.1)
    terminal.symbol_select = lambda *args: True
    def bars(symbol, tf, start, end):
        terminal.calls.append('bars')
        return [dict(time=int(t.timestamp()), open=100, high=102, low=99, close=101,
                     tick_volume=10, real_volume=0, spread=2)
                for t in pd.date_range(start, end, freq='min')]
    def ticks(symbol, start, end, flags):
        terminal.calls.append('ticks')
        return [dict(time_msc=int(start.timestamp()*1000), bid=100, ask=100.2, last=0,
                     volume=0, volume_real=0, flags=6)] * 2
    terminal.copy_rates_range = bars
    terminal.copy_ticks_range = ticks


def request(kind='1m', **kwargs):
    return dict(symbol='NASUSD', data_type=kind, start='2026-01-02T10:00:00Z',
                end='2026-01-02T10:03:00Z', **kwargs)


def test_columnar_cache_reuse_and_volume_provenance(setup):
    service, terminal, db = setup
    wire(terminal)
    result = service.market_history('mt5-default', request())
    assert result['rows'] == 3 and result['canonical_symbol'] is None
    assert result['instrument_type'] == 'cfd'
    assert result['fields']['real_volume']['positive_rows'] == 0
    assert result['fields']['tick_volume']['positive_rows'] == 3
    assert result['coverage_complete'] is False
    assert result['observed_end'] == '2026-01-02T10:02:00+00:00'
    path = db.path.parent/'market'/'mt5-hub'/(result['data_fingerprint']+'.parquet')
    with duckdb.connect() as connection:
        frame = connection.execute('SELECT * FROM read_parquet(?)', [str(path)]).df()
    assert frame.real_volume.tolist() == [0]*3 and 'volume' not in frame
    before = list(terminal.calls)
    assert service.market_history('mt5-default', request())['cache_hit']
    assert terminal.calls == before
    assert service.market_history('mt5-default')['items'][0]['data_fingerprint'] == result['data_fingerprint']


def test_ticks_preserve_same_timestamp_events_and_missing_last(setup):
    service, terminal, db = setup
    wire(terminal)
    result = service.market_history('mt5-default', request('ticks'))
    assert result['rows'] == 2
    assert result['fields']['last']['non_null_rows'] == 0
    assert result['fields']['bid']['non_null_rows'] == 2
    assert result['fields']['spread_price']['positive_rows'] == 2
    assert result['fields']['last_trade_volume_real']['positive_rows'] == 0
    assert 'tick_volume' not in result['fields']


@pytest.mark.parametrize('change', [dict(start='2026-01-02T10:00'), dict(data_type='bogus'),
    dict(end='2099-01-02T10:00Z'), dict(end='2025-01-02T10:00Z'),
    dict(data_type='ticks',end='2026-01-04T10:00Z')])
def test_invalid_requests_rejected_before_provider(setup, change):
    service, terminal, db = setup
    before = list(terminal.calls)
    with pytest.raises(BrokerHistoryError):
        service.market_history('mt5-default', {**request(), **change})
    assert terminal.calls == before


@pytest.mark.parametrize('failure', ['none','empty','invalid','account','conflict'])
def test_failure_does_not_publish_coverage(setup, failure):
    service, terminal, db = setup
    wire(terminal)
    original = terminal.copy_rates_range
    def bad(*args):
        if failure == 'none': return None
        if failure == 'empty': return []
        rows = original(*args)
        if failure == 'invalid': rows[0]['high'] = 50
        if failure == 'account': terminal.login = 456
        if failure == 'conflict': rows.append({**rows[0], 'close':100.5})
        return rows
    terminal.copy_rates_range = bad
    with pytest.raises(BrokerHistoryError):
        service.market_history('mt5-default', request())
    assert service.market_history('mt5-default')['items'] == []
    assert terminal.calls[-1] == 'shutdown'


def test_incomplete_bar_and_utc_equivalent_requests(setup):
    service, terminal, db = setup
    wire(terminal)
    result = service.market_history('mt5-default', {**request(), 'end':'2026-01-02T10:02:30Z'})
    assert result['rows'] == 2
    a = history_request(**request())
    b = history_request(**{**request(), 'start':'2026-01-02T11:00:00+01:00'})
    assert a == b


def test_cache_corruption_fails_closed_without_terminal_call(setup):
    service, terminal, db = setup
    wire(terminal)
    result = service.market_history('mt5-default', request())
    path = db.path.parent/'market'/'mt5-hub'/(result['data_fingerprint']+'.parquet')
    path.write_bytes(b'corrupt')
    before = list(terminal.calls)
    with pytest.raises(BrokerHistoryError, match='integrity'):
        service.market_history('mt5-default', request())
    assert before == terminal.calls


def test_tick_windows_and_budget_are_explicit(setup, monkeypatch):
    service, terminal, db = setup
    wire(terminal)
    result = service.market_history('mt5-default', {**request('ticks'), 'end':'2026-01-02T12:00Z'})
    assert result['rows'] == 4 and terminal.calls.count('ticks') == 2
    monkeypatch.setattr('app.data.mt5_history.MAX_ROWS', 1)
    with pytest.raises(BrokerHistoryError, match='smaller window'):
        service.market_history('mt5-default', request('ticks'))
    assert len(service.market_history('mt5-default')['items']) == 1


def test_missing_symbol_and_crossed_quotes_reject(setup):
    service, terminal, db = setup
    wire(terminal)
    terminal.symbol_info = lambda name: None
    with pytest.raises(BrokerHistoryError, match='no alias'):
        service.market_history('mt5-default', request())
    wire(terminal)
    terminal.copy_ticks_range = lambda *a: [dict(time_msc=int(pd.Timestamp('2026-01-02T10:00Z').timestamp()*1000), bid=101,ask=100)]
    with pytest.raises(BrokerHistoryError, match='Invalid'):
        service.market_history('mt5-default', request('ticks'))
    assert service.market_history('mt5-default')['items'] == []


def test_api_history_and_coverage(setup):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.brokers import router
    from app.api.dependencies import get_services
    service, terminal, db = setup
    wire(terminal)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_services] = lambda: NS(broker_connections=service)
    with TestClient(app) as client:
        response = client.post('/brokers/mt5-default/market-history', json=request())
        assert response.status_code == 200 and response.json()['rows'] == 3
        assert len(client.get('/brokers/mt5-default/market-coverage').json()['items']) == 1
        assert client.post('/brokers/mt5-default/market-history', json={**request(), 'data_type':'invalid'}).status_code == 422
