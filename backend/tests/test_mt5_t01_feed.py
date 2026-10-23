from datetime import datetime, timezone
from threading import Lock
from types import SimpleNamespace as NS

import pytest

from app.brokers.base import BrokerHistoryError
from app.brokers.profiles import BrokerProfile
from app.forward.mt5_t01_feed import collect, read_minute

NOW = datetime(2026, 1, 5, 1, 1, 2, tzinfo=timezone.utc)
START = NOW.replace(minute=0, second=0)


@pytest.fixture
def feed():
    account = NS(trade_mode=0, currency='USD', equity=10000.)
    terminal = NS(connected=True)
    quote = NS(time_msc=int(NOW.timestamp()*1000), bid=3000., ask=3000.2)
    rows = [dict(time=int(START.timestamp()), open=3000., high=3002., low=2998., close=3001., tick_volume=7)]
    calls = []
    module = NS(ACCOUNT_TRADE_MODE_DEMO=0, TIMEFRAME_M1=1,
        terminal_info=lambda:terminal, positions_get=lambda:[], orders_get=lambda:[],
        symbol_info=lambda symbol:NS(name=symbol), symbol_select=lambda *args:True,
        symbol_info_tick=lambda symbol:quote,
        copy_rates_range=lambda *args:(calls.append(('rates',args)) or rows))
    adapter = NS(_module=module, _clock=lambda:NOW.timestamp(), environment='demo',
        account_key='a'*64, currency='USD', _account=lambda:(account, 'a'*64),
        connect=lambda key:calls.append(('connect',key)), close=lambda:calls.append(('close',)))
    definition = dict(account_key='a'*64, currency='USD', environment='demo',
        symbol='XAUUSDs', timestamp_policy='verified_utc')
    profile = BrokerProfile('fixture','mt5','demo',credentials=dict(terminal_path='fixture.exe',
        login='SECRET_LOGIN',password='SECRET_PASSWORD',server='SECRET_SERVER'))
    def factory(credentials, environment):
        calls.append(('factory',dict(credentials),environment)); return adapter
    connections = NS(_profile=lambda key:profile, _profile_locks={'fixture':Lock()},
        _selection=lambda p:'selected', _setting=lambda key:'a'*64, factories={'mt5':factory})
    return adapter, module, account, terminal, quote, rows, calls, definition, connections, profile


def run(feed, **changes):
    return collect(feed[0], symbol='XAUUSDs', expected_start=START,
                   **(dict(timestamp_policy='verified_utc') | changes))


def test_reads_only_exact_completed_minute_with_tick_volume(feed):
    feed[5].append(dict(feed[5][0], time=int(START.timestamp())+60, high=999999))
    result = run(feed)
    assert result['bar']['high'] == 3002 and result['bar']['volume'] == 7
    assert result['volume_basis'] == 'mt5_tick_volume' and result['position'] is None
    assert not result['execution_enabled'] and result['equity'] == 10000
    assert feed[6][0][1][2:] == (START, START.replace(minute=1))


@pytest.mark.parametrize('offset', [7200,10800,-10,1])
def test_shifted_stale_or_future_quotes_are_not_corrected(feed, offset):
    feed[4].time_msc += offset*1000
    with pytest.raises(BrokerHistoryError, match='UTC quote freshness'):
        run(feed)
    assert feed[6] == []


@pytest.mark.parametrize('failure', ['position','order','disconnected','live','currency','identity','nan','crossed','unverified_bridge'])
def test_unsafe_or_unknown_observation_rejected(feed, failure):
    adapter, module, account, terminal, quote = feed[:5]
    if failure == 'position': module.positions_get = lambda:[NS()]
    if failure == 'order': module.orders_get = lambda:[NS()]
    if failure == 'disconnected': terminal.connected = False
    if failure == 'live': account.trade_mode = 2
    if failure == 'currency': account.currency = 'EUR'
    if failure == 'identity': adapter._account = lambda:(account,'b'*64)
    if failure == 'nan': account.equity = float('nan')
    if failure == 'crossed': quote.ask = 2999.
    if failure == 'unverified_bridge': module.timestamp_policy = 'unverified'
    with pytest.raises(BrokerHistoryError): run(feed)


@pytest.mark.parametrize('failure', ['empty','duplicate','future','bad_ohlc','shifted_bar','exception','position_appeared','account_changed'])
def test_failed_read_rejects_snapshot_and_sanitizes_errors(feed, failure):
    adapter, module, account = feed[:3]
    def broken(*args):
        rows = feed[5]
        if failure == 'empty': return []
        if failure == 'duplicate': return rows*2
        if failure == 'future': return [dict(rows[0],time=rows[0]['time']+120)]
        if failure == 'bad_ohlc': return [dict(rows[0],high=1)]
        if failure == 'shifted_bar': return [dict(rows[0],time=rows[0]['time']+10800)]
        if failure == 'exception': raise RuntimeError('SECRET_NATIVE_FAILURE')
        if failure == 'position_appeared': module.positions_get = lambda:[NS()]
        if failure == 'account_changed': adapter._account = lambda:(account,'b'*64)
        return rows
    module.copy_rates_range = broken
    with pytest.raises(BrokerHistoryError) as error: run(feed)
    assert 'SECRET' not in str(error.value)


def test_overlap_detects_provider_revisions(feed):
    previous = dict(timestamp=START.replace(hour=0,minute=59).isoformat(), available_at=START.isoformat(),
        open=3000.,high=3002.,low=2998.,close=3001.,volume=7.)
    feed[5].insert(0, dict(feed[5][0],time=int(START.timestamp())-60))
    assert run(feed, previous_bar=previous)['bar']['timestamp'] == START.isoformat()
    feed[5][0]['close'] = 3000.
    with pytest.raises(BrokerHistoryError): run(feed, previous_bar=previous)


def test_expired_or_clock_rollback_observation_rejected(feed):
    for delta in (6,-1,60):
        readings = iter([NOW.timestamp(),NOW.timestamp(),NOW.timestamp()+delta])
        feed[0]._clock = lambda:next(readings)
        with pytest.raises(BrokerHistoryError): run(feed)


def test_quote_can_advance_while_the_native_read_is_in_progress(feed):
    readings = iter([NOW.timestamp(),NOW.timestamp()+.5,NOW.timestamp()+1])
    feed[0]._clock = lambda:next(readings)
    feed[4].time_msc += 250
    assert run(feed)['bar']['timestamp'] == START.isoformat()


def test_profile_lifecycle_uses_no_login_credentials_and_releases_locks(feed):
    result = read_minute(feed[8], 'fixture', feed[7], expected_start=START)
    assert result['environment'] == 'demo'
    credentials = feed[6][0][1]
    assert set(credentials) == {'terminal_path','bridge_url','bridge_token_file'}
    assert 'SECRET' not in str(feed[6])
    assert feed[6][-1] == ('close',) and not feed[8]._profile_locks['fixture'].locked()


@pytest.mark.parametrize('failure', ['live','disabled','selection','default_terminal','busy','unverified'])
def test_profile_rejections_do_not_initialize_terminal(feed, failure):
    if failure == 'live': feed[9].environment = 'live'
    if failure == 'disabled': feed[9].enabled = False
    if failure == 'selection': feed[8]._setting = lambda key:'b'*64
    if failure == 'default_terminal': feed[9].credentials = {}
    if failure == 'busy': feed[8]._profile_locks['fixture'].acquire()
    if failure == 'unverified': feed[7]['timestamp_policy'] = 'unverified'
    with pytest.raises(BrokerHistoryError):
        read_minute(feed[8], 'fixture', feed[7], expected_start=START)
    assert feed[6] == []


def test_read_failure_always_closes_adapter_and_releases_profile_lock(feed):
    feed[1].copy_rates_range = lambda *args:None
    with pytest.raises(BrokerHistoryError):
        read_minute(feed[8], 'fixture', feed[7], expected_start=START)
    assert feed[6][-1] == ('close',)
    assert not feed[8]._profile_locks['fixture'].locked()


@pytest.mark.parametrize('entry', ['collect','profile'])
def test_research_context_cannot_probe_the_demo_feed(feed, entry):
    from app.research_agent.access import preparation_scope
    with preparation_scope(None, 'fixture-campaign'):
        with pytest.raises(ValueError, match='Research cannot'):
            if entry == 'collect': run(feed)
            else: read_minute(feed[8], 'fixture', feed[7], expected_start=START)
    assert feed[6] == []
