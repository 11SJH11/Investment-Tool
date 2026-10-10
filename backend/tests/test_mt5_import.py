from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from app.brokers.base import BrokerHistoryError
from app.brokers.metatrader5 import MetaTrader5History
from app.core.config import Settings
from app.services.broker_connections import BrokerConnections
from app.storage.database import Database
from app.storage.journal_repository import JournalRepository


def deal(ticket, entry, side, volume, price, profit=0, commission=-1, swap=0, fee=0, position=10):
    return NS(ticket=ticket, order=ticket+100, position_id=position, entry=entry, type=side,
              volume=volume, price=price, profit=profit, commission=commission, swap=swap, fee=fee,
              symbol='EURUSD.b', time=ticket, time_msc=ticket*1000)


class Terminal:
    def __init__(self):
        self.deals = [deal(1, 0, 0, 2, 100), deal(2, 1, 1, 2, 110, 20)]
        self.account = NS(login=777, server='fixture-server', currency='USD', trade_mode=0)
        self.calls = []
        self.now = 10
        self.fail = False
        self.unknown = False
        self.shutdowns = 0

    def initialize(self, *args, **kwargs):
        self.calls.append(('initialize', args, kwargs)); return True

    def shutdown(self):
        self.shutdowns += 1

    def account_info(self):
        return self.account

    def positions_get(self):
        return []

    def history_deals_get(self, *args, **kwargs):
        self.calls.append(('history', args, kwargs))
        if self.fail: return None
        if 'position' in kwargs: return [d for d in self.deals if d.position_id == kwargs['position']]
        return [d for d in self.deals if args[0].timestamp()*1000 <= d.time_msc <= args[1].timestamp()*1000]

    def symbol_info(self, symbol):
        return None if self.unknown else NS(name=symbol, trade_contract_size=100000, currency_profit='USD')

    def factory(self, credentials, environment):
        return MetaTrader5History(credentials, environment, module=self, clock=lambda: self.now)


@pytest.fixture
def setup(tmp_path):
    db = Database(tmp_path/'db'); db.initialize(); terminal = Terminal()
    connections = BrokerConnections(Settings(_env_file=None, MT5_ENABLED=True), db, factories={'mt5': terminal.factory})
    return db, terminal, connections


@pytest.mark.parametrize('short', [False, True])
def test_long_short_money_identity_and_lots(setup, short):
    db, t, s = setup
    if short:
        for d in t.deals: d.type = 1-d.type
    assert s.sync('mt5-default')['created'] == 1
    row = JournalRepository(db).list_trades()[0]
    assert row['direction'] == ('short' if short else 'long')
    assert row['broker_realized_pnl'] == 20 and row['pnl_amount'] == 18
    assert row['commission'] == 2 and row['quantity'] == 2
    assert row['source_metadata']['quantity_unit'] == 'lots'
    assert row['source_metadata']['executions'][0]['metadata']['current_contract_size'] == '100000'
    assert t.shutdowns == 1
    assert s.sync('mt5-default')['executions_changed'] == 0
    assert len(JournalRepository(db).list_trades()) == 1


def test_scale_in_out_multiple_fills_swaps_and_reconnect(setup):
    db, t, s = setup
    t.deals = [deal(1, 0, 0, 1, 100), deal(2, 0, 0, 2, 103),
               deal(3, 1, 1, 1, 110, 8, swap=-2, fee=-.5)]
    assert s.sync('mt5-default')['created'] == 0
    t.deals.append(deal(4, 1, 1, 2, 115, 26, swap=-1))
    assert s.sync('mt5-default')['executions_changed'] == 1
    row = JournalRepository(db).list_trades()[0]
    assert row['entry_price'] == 102 and row['exit_price'] == pytest.approx(340/3)
    assert row['quantity'] == 3 and row['broker_realized_pnl'] == 34
    assert row['pnl_amount'] == 26.5 and row['financing'] == -3 and row['fees'] == 4.5
    other = BrokerConnections(Settings(_env_file=None, MT5_ENABLED=True), db, factories={'mt5': t.factory})
    assert other.sync('mt5-default')['created'] == 0
    assert JournalRepository(db).list_trades()[0]['id'] == row['id']


def test_incremental_window_fetches_full_older_position_history(setup):
    db, t, s = setup
    t.deals = [deal(1, 0, 0, 1, 100)]
    t.now = 200000
    s.sync('mt5-default')
    closing = deal(200001, 1, 1, 1, 110, 10); t.deals.append(closing); t.now += 2
    assert s.sync('mt5-default')['created'] == 1
    scans = [call for call in t.calls if call[0]=='history' and call[1]]
    assert scans[-1][1][0].timestamp() == 200000 - 86400
    assert all(call[1][0].tzinfo is not None for call in scans)


@pytest.mark.parametrize('failure', ['unknown', 'missing_open', 'reversal', 'failure', 'environment'])
def test_failures_preserve_journal_and_cursor(setup, failure):
    db, t, s = setup; s.sync('mt5-default')
    before = JournalRepository(db).list_trades()
    key = before[0]['external_account_key']; cursor = s.state.state('mt5', key)['cursor']
    if failure == 'unknown': t.unknown = True
    if failure == 'missing_open': t.deals = [deal(3, 1, 1, 1, 120, position=11)]
    if failure == 'reversal': t.deals.append(deal(3, 2, 1, 3, 120))
    if failure == 'failure': t.fail = True
    if failure == 'environment': t.account.trade_mode = 2
    with pytest.raises(BrokerHistoryError): s.sync('mt5-default')
    assert JournalRepository(db).list_trades() == before
    assert s.state.state('mt5', key)['cursor'] == cursor


def test_terminal_access_serialized_and_release_after_failure():
    t = Terminal(); a = t.factory({}, 'demo'); b = t.factory({}, 'demo')
    try:
        a.connect()
        with pytest.raises(BrokerHistoryError, match='busy'): b.connect()
    finally:
        a.close(); b.close()
    c = t.factory({}, 'demo')
    try: assert c.connect()['environment'] == 'demo'
    finally: c.close()


def test_missing_optional_package_is_safe(monkeypatch):
    def missing(name): raise ImportError('sensitive native detail')
    monkeypatch.setattr('app.brokers.metatrader5.importlib.import_module', missing)
    a = MetaTrader5History({}, 'demo')
    with pytest.raises(BrokerHistoryError, match='optional') as error: a.connect()
    assert 'sensitive' not in str(error.value)
    a.close()


def test_multiple_accounts_and_environments_do_not_collide(setup):
    db, t, s = setup; s.sync('mt5-default')
    t.account.login = 888
    key = s.discover('mt5-default')['items'][0]['account_key']; s.select_account('mt5-default', key)
    s.sync('mt5-default')
    t.account.trade_mode = 2; s.profiles['mt5-default'].environment = 'live'
    key = s.discover('mt5-default')['items'][0]['account_key']; s.select_account('mt5-default', key)
    s.sync('mt5-default')
    assert len(JournalRepository(db).list_trades()) == 3


def test_position_linked_cash_adjustment_is_not_silently_discarded(setup):
    db,t,s=setup
    adjustment=deal(3,0,7,0,0,profit=-5)
    t.deals.append(adjustment)
    with pytest.raises(BrokerHistoryError,match='separate cash adjustments'):
        s.sync('mt5-default')
    assert JournalRepository(db).list_trades()==[]


def test_native_shutdown_error_is_sanitized_and_releases_terminal_lock(caplog):
    t=Terminal();a=t.factory({},'demo');a.connect()
    def fail():raise RuntimeError('native-password-secret')
    t.shutdown=fail;a.close()
    assert 'native-password-secret' not in caplog.text
    assert 'IPC disconnect failed' in caplog.text
    b=Terminal().factory({},'demo')
    try:assert b.connect()['environment']=='demo'
    finally:b.close()


@pytest.mark.parametrize('entry_reason,exit_reason,expected',[(3,4,True),(None,3,None),(0,4,None)])
def test_automation_requires_programmatic_entry_evidence(setup,entry_reason,exit_reason,expected):
    db,t,s=setup;t.DEAL_REASON_EXPERT=3
    t.deals[0].reason=entry_reason;t.deals[1].reason=exit_reason
    s.sync('mt5-default');row=JournalRepository(db).list_trades()[0]
    assert row['is_automated'] is expected and row['execution_source']=='imported'
    assert row['source_metadata']['executions'][0]['metadata']['deal_reason']==entry_reason
    assert s.sync('mt5-default')['created']==0
