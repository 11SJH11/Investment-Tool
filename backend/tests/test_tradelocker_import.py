"""Official endpoint fixtures only; no credentials, terminal or network required."""
from copy import deepcopy
import json

import httpx
import pytest

from app.brokers.base import BrokerHistoryError
from app.brokers.tradelocker import TradeLockerHistory
from app.core.config import Settings
from app.services.broker_connections import BrokerConnections
from app.storage.database import Database
from app.storage.journal_repository import JournalRepository
from app.services.journal import JournalService


COLUMNS = ['id', 'tradableInstrumentId', 'routeId', 'qty', 'side', 'status', 'filledQty', 'avgPrice', 'createdDate', 'lastModified', 'isOpen', 'positionId']


def order(id, side, qty, price, stamp, position=10):
    return dict(zip(COLUMNS, [id, 1, 1, qty, side, 'Filled', qty, price, stamp, stamp, False, position]))


class Provider:
    def __init__(self):
        self.calls = []
        self.rows = [order(1, 'buy', 2, 100, 1000), order(2, 'sell', 1, 110, 2000), order(3, 'sell', 1, 120, 3000)]
        self.accounts = [dict(id=777, accNum=22, currency='USD')]
        self.positions = []
        self.cap = 100
        self.failure = None
        self.unknown_symbol = False
        self.now = 10

    def handler(self, request):
        self.calls.append(request)
        path = request.url.path
        if path.endswith('/auth/jwt/token'):
            assert request.method == 'POST'
            assert json.loads(request.content)['email'] == 'synthetic-email'
            return httpx.Response(200, json={'accessToken': 'synthetic-token'})
        assert request.method == 'GET'
        assert request.headers['authorization'] == 'Bearer synthetic-token'
        if self.failure and path.endswith(self.failure):
            return httpx.Response(429, headers={'Retry-After': '90'}, json={'error': 'synthetic-password account-secret'})
        if path.endswith('/all-accounts'):
            return httpx.Response(200, json={'accounts': self.accounts})
        assert request.headers['accNum'] == str(self.accounts[0]['accNum'])
        if path.endswith('/config'):
            data = dict(ordersHistoryConfig={'columns': [{'id': c} for c in COLUMNS]},
                positionsConfig={'columns': [{'id': 'id'}]},
                limits=[{'limitType': 'MAX_ORDERS_COUNT_IN_HISTORY', 'limit': self.cap}],
                rateLimits=[dict(rateLimitType='GET_ORDERS_HISTORY', measure='SECONDS', intervalNum=1, limit=1)])
        elif path.endswith('/ordersHistory'):
            start, end = int(request.url.params['from']), int(request.url.params['to'])
            data = {'ordersHistory': [[r[c] for c in COLUMNS] for r in self.rows if start <= r['createdDate'] <= end][:self.cap]}
        elif path.endswith('/instruments'):
            data = {'instruments': [] if self.unknown_symbol else [dict(tradableInstrumentId=1, name='EURUSD.broker', type='FOREX')]}
        elif path.endswith('/positions'):
            data = {'positions': [[id] for id in self.positions]}
        else:
            pytest.fail('Unexpected route: ' + path)
        return httpx.Response(200, json={'s': 'ok', 'd': data})

    def factory(self, credentials, environment):
        return TradeLockerHistory(credentials, environment, client=httpx.Client(transport=httpx.MockTransport(self.handler)),
                                  clock=lambda: self.now, sleep=lambda delay: setattr(self, 'now', self.now + delay))


@pytest.fixture
def setup(tmp_path):
    db = Database(tmp_path/'db'); db.initialize()
    provider = Provider()
    settings = Settings(_env_file=None, TRADELOCKER_ENABLED=True, TRADELOCKER_EMAIL='synthetic-email',
                        TRADELOCKER_PASSWORD='synthetic-password', TRADELOCKER_SERVER='synthetic-server')
    connections = BrokerConnections(settings, db, factories={'tradelocker': provider.factory})
    return db, provider, connections


def select(connections):
    key = connections.discover('tradelocker-default')['items'][0]['account_key']
    connections.select_account('tradelocker-default', key)
    return key


def test_full_sync_partial_closes_idempotency_review_and_atomic_cursor(setup):
    db, p, s = setup
    assert s.status('tradelocker-default')['configured'] and not p.calls
    key = select(s)
    result = s.sync('tradelocker-default')
    assert (result['created'], result['executions_changed']) == (1, 3)
    repo = JournalRepository(db); row = repo.list_trades()[0]
    assert row['entry_price'] == 100 and row['exit_price'] == 115 and row['quantity'] == 2
    assert row['pnl_amount'] is None and row['broker_realized_pnl'] is None and row['fees'] is None
    assert row['ticker'] == 'EURUSD.broker' and not row['costs_complete']
    assert row['opened_at'] == '1970-01-01T00:00:01+00:00'
    assert row['source_metadata']['timestamp_basis'] == 'order_last_modified'
    JournalService(repo).update_trade(row['id'], {'notes': 'Keep my review'})
    repo.add_attachment(dict(owner_type='trade', owner_id=row['id'], original_name='proof.png', stored_name='proof.png', mime_type='image/png'))
    assert s.sync('tradelocker-default')['executions_changed'] == 0
    assert len(repo.list_trades()) == 1
    p.rows[-1]['avgPrice'] = 122
    assert s.sync('tradelocker-default')['updated'] == 1
    assert repo.get_trade(row['id'])['notes'] == 'Keep my review'
    assert repo.get_trade(row['id'])['exit_price'] == 116
    before = repo.get_trade(row['id']); cursor = s.state.state('tradelocker', key)['cursor']
    p.failure = '/ordersHistory'
    with pytest.raises(BrokerHistoryError) as exc:
        s.sync('tradelocker-default')
    assert exc.value.retry_after == 90 and exc.value.category == 'rate_limited'
    assert repo.get_trade(row['id']) == before and s.state.state('tradelocker', key)['cursor'] == cursor
    assert len(repo.attachments('trade', row['id'])) == 1
    db.initialize(); db.initialize()
    assert repo.get_trade(row['id']) == before
    serialized = json.dumps([s.statuses(), repo.list_trades(), s.state.executions('tradelocker', key)])
    assert all(secret not in serialized for secret in ('synthetic-password', 'synthetic-token', 'synthetic-email', 'synthetic-server'))


def test_partial_open_history_persists_then_closes_incrementally(setup):
    db, p, s = setup; select(s)
    final = p.rows.pop()
    assert s.sync('tradelocker-default')['created'] == 0
    p.rows.append(final)
    result = s.sync('tradelocker-default')
    assert result['created'] == 1 and result['executions_changed'] == 1
    assert len(JournalRepository(db).list_trades()) == 1


def test_bounded_windowing_deduplicates_inclusive_boundaries(setup):
    _, p, s = setup; select(s); p.cap = 2
    assert s.sync('tradelocker-default')['created'] == 1
    assert len([r for r in p.calls if r.url.path.endswith('/ordersHistory')]) > 1


def test_saturated_minimum_window_preserves_data(setup):
    db, p, s = setup; select(s); p.cap = 2
    for row in p.rows:
        row['createdDate'] = row['lastModified'] = 1000
    with pytest.raises(BrokerHistoryError, match='saturated'):
        s.sync('tradelocker-default')
    assert JournalRepository(db).list_trades() == []


@pytest.mark.parametrize('failure', ['unknown', 'nan', 'missing_open', 'reversal'])
def test_incomplete_or_ambiguous_history_is_not_guessed(setup, failure):
    db, p, s = setup; select(s)
    if failure == 'unknown': p.unknown_symbol = True
    if failure == 'nan': p.rows[0]['avgPrice'] = 'NaN'
    if failure == 'missing_open': p.rows.pop(0)
    if failure == 'reversal': p.rows[-1]['filledQty'] = 3
    if failure == 'missing_open':
        # Unbalanced aggregate history remains pending; no made-up closed trade.
        assert s.sync('tradelocker-default')['created'] == 0
    else:
        with pytest.raises(BrokerHistoryError): s.sync('tradelocker-default')
    assert JournalRepository(db).list_trades() == []


def test_unknown_selection_and_unconfigured_make_no_history_calls(setup):
    db, p, s = setup
    with pytest.raises(BrokerHistoryError, match='Select'):
        s.sync('tradelocker-default')
    assert not any(r.url.path.endswith('/ordersHistory') for r in p.calls)
    empty = BrokerConnections(Settings(_env_file=None), db, factories={'tradelocker': lambda *a: pytest.fail('unconfigured network')})
    assert empty.sync('tradelocker-default')['status'] == 'not_configured'


def test_account_and_environment_identity_do_not_collide(setup):
    db, p, s = setup
    key = select(s); s.sync('tradelocker-default')
    p.accounts[0]['id'] = 888
    other = select(s); s.sync('tradelocker-default')
    assert key != other
    s.profiles['tradelocker-default'].environment = 'live'
    live = select(s); s.sync('tradelocker-default')
    assert live not in {key, other}
    assert len(JournalRepository(db).list_trades()) == 3


def test_auth_errors_do_not_echo_provider_body_or_credentials(setup):
    _, p, s = setup
    p.failure = '/all-accounts'
    with pytest.raises(BrokerHistoryError) as exc:
        s.discover('tradelocker-default')
    assert 'synthetic-password' not in str(exc.value) and 'account-secret' not in str(exc.value)


def test_httpx_optional_logging_redacts_account_paths(setup, caplog):
    import logging
    _,p,s=setup
    caplog.set_level(logging.INFO,logger='httpx')
    select(s);s.sync('tradelocker-default')
    assert '/accounts/777' not in caplog.text
    assert '/accounts/[account]' in caplog.text
    assert all(value not in caplog.text for value in ('synthetic-password','synthetic-token','synthetic-email'))


def test_late_opening_order_modification_cannot_reverse_trade_direction(setup):
    db,p,s=setup;select(s)
    p.rows[0]['lastModified']=4000
    with pytest.raises(BrokerHistoryError,match='chronology'):
        s.sync('tradelocker-default')
    assert JournalRepository(db).list_trades()==[]
