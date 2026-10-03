"""Official TradeLocker Public API: authentication + allowlisted GETs only.

Historical order aggregates are deliberately labelled, not represented as deals.
Config-driven row caps, bounded window splitting and provider cooldowns fail
without advancing reconciliation state. No SDK execution methods are imported.
"""
import time

import httpx

from app.brokers.base import BrokerHistoryError
from app.brokers.executions import Execution, ExecutionBatch, account_key, identity, number, utc_millis
from app.data.http import _retry_delay
from app.brokers.log_safety import protect_broker_http_logs


class TradeLockerHistory:
    provider = 'tradelocker'

    def __init__(self, credentials, environment, *, client=None, clock=time.time, sleep=time.sleep):
        if environment not in {'demo', 'live'} or not all(credentials.get(k, '').strip() for k in ('email', 'password', 'server')):
            raise BrokerHistoryError('TradeLocker credentials are incomplete', category='configuration')
        self.environment, self._credentials = environment, dict(credentials)
        protect_broker_http_logs()
        self._client = client or httpx.Client(timeout=30, follow_redirects=False)
        self._clock, self._sleep = clock, sleep
        self._base = f'https://{environment}.tradelocker.com/backend-api'
        self._token = None
        self._account = None
        self._config = None
        self._next_history = 0
        self._requests = 0
        self.account_key = self.account_label = self.currency = None

    @staticmethod
    def capability_report():
        return dict(provider='tradelocker', destination='journal', supported=True, read_only=True,
                    execution=False, closed_trades=True, account_discovery=True,
                    reason='Historical order aggregates; exact deal timestamps and unreported costs/P&L remain unavailable. No order execution.')

    def close(self):
        self._token = None
        self._credentials.clear()
        self._client.close()

    def _request(self, path, *, params=None, authentication=False):
        allowed = {'/auth/jwt/token', '/auth/jwt/all-accounts', '/trade/config'}
        if self._account:
            prefix = '/trade/accounts/' + identity(self._account['id'])
            allowed.update(prefix + '/' + name for name in ('ordersHistory', 'instruments', 'positions'))
        if path not in allowed or authentication != (path == '/auth/jwt/token'):
            raise BrokerHistoryError('TradeLocker operation is not permitted', category='configuration')
        headers = {}
        if self._credentials.get('developer_api_key'):
            headers['developer-api-key'] = self._credentials['developer_api_key']
        if not authentication:
            if not self._token:
                auth = self._request('/auth/jwt/token', authentication=True)
                self._token = auth.get('accessToken')
                if not isinstance(self._token, str) or not self._token:
                    raise BrokerHistoryError('TradeLocker authentication failed', category='authentication')
            headers['Authorization'] = 'Bearer ' + self._token
        if path.startswith('/trade/'):
            headers['accNum'] = str(self._account['accNum'])
        try:
            if authentication:
                response = self._client.post(self._base + path, headers=headers,
                    json={k: self._credentials[k] for k in ('email', 'password', 'server')}, follow_redirects=False)
            else:
                response = self._client.get(self._base + path, params=params, headers=headers, follow_redirects=False)
            if response.status_code == 429:
                raise BrokerHistoryError('TradeLocker rate limit reached; previous data retained',
                    status_code=429, retry_after=max(60, _retry_delay(response, 1)), category='rate_limited')
            if response.status_code != 200:
                category = 'authentication' if response.status_code == 401 else 'permission' if response.status_code == 403 else 'provider'
                raise BrokerHistoryError('TradeLocker request failed; check connection and read permissions',
                                         status_code=response.status_code, category=category)
            body = response.json()
            if not isinstance(body, dict) or body.get('s', 'ok') != 'ok':
                raise ValueError()
            return body
        except BrokerHistoryError:
            raise
        except Exception:
            raise BrokerHistoryError('TradeLocker returned unavailable or invalid data', category='provider') from None

    def accounts(self):
        try:
            items = self._request('/auth/jwt/all-accounts')['accounts']
            if not isinstance(items, list):
                raise ValueError()
            result = []
            self._accounts = {}
            for account in items:
                raw_id = identity(account['id'])
                if not raw_id.isdecimal() or not identity(account['accNum']).isdecimal():
                    raise ValueError()
                key = account_key(self.provider, self.environment, self._credentials['server'], raw_id)
                if key in self._accounts:
                    raise ValueError()
                self._accounts[key] = account
                result.append(dict(account_key=key, environment=self.environment,
                    label=f'TradeLocker {self.environment} / {key[:8]}', currency=account['currency']))
            return result
        except BrokerHistoryError:
            raise
        except Exception:
            raise BrokerHistoryError('TradeLocker account discovery returned invalid data', category='provider') from None

    def connect(self, selected_key=None):
        accounts = self.accounts()
        if selected_key is None and self._credentials.get('account_id'):
            selected_key = account_key(self.provider, self.environment, self._credentials['server'], self._credentials['account_id'])
        if selected_key not in self._accounts:
            raise BrokerHistoryError('Select a verified TradeLocker account before syncing', category='configuration')
        self._account = self._accounts[selected_key]
        selected = next(a for a in accounts if a['account_key'] == selected_key)
        self.account_key, self.account_label, self.currency = selected_key, selected['label'], selected['currency']
        self._config = self._request('/trade/config').get('d')
        if not isinstance(self._config, dict):
            raise BrokerHistoryError('TradeLocker configuration is unavailable', category='provider')
        return selected

    def _rows(self, endpoint, config_name, params=None):
        body = self._request(f'/trade/accounts/{self._account["id"]}/{endpoint}', params=params)
        try:
            columns = [c['id'] for c in self._config[config_name]['columns']]
            rows = body['d'][endpoint]
            if not isinstance(rows, list) or len(columns) != len(set(columns)):
                raise ValueError()
            if any(not isinstance(row, list) or len(row) != len(columns) for row in rows):
                raise ValueError()
            return [dict(zip(columns, row)) for row in rows]
        except (KeyError, TypeError, ValueError):
            raise BrokerHistoryError('TradeLocker history columns do not match its configuration', category='history') from None

    def _history(self, start, end, cap, interval, deadline):
        self._requests += 1
        wait = max(0, self._next_history - self._clock())
        if self._requests > 512 or self._clock() + wait > deadline or wait > 60:
            raise BrokerHistoryError('TradeLocker history exceeded its safe request budget; cursor retained', category='history')
        if wait:
            self._sleep(wait)
        rows = self._rows('ordersHistory', 'ordersHistoryConfig', {'from': start, 'to': end})
        self._next_history = self._clock() + interval
        if len(rows) >= cap:
            if end - start <= 1:
                raise BrokerHistoryError('TradeLocker history window is saturated; complete fills cannot be verified', category='history')
            middle = (start + end) // 2
            # Inclusive overlap avoids assuming undocumented boundary exclusivity.
            return self._history(start, middle, cap, interval, deadline) + self._history(middle, end, cap, interval, deadline)
        return rows

    def read_executions(self, cursor):
        try:
            limits = [int(x['limit']) for x in self._config['limits'] if x['limitType'] == 'MAX_ORDERS_COUNT_IN_HISTORY']
            rates = [x for x in self._config['rateLimits'] if x['rateLimitType'] == 'GET_ORDERS_HISTORY']
            if len(limits) != 1 or limits[0] <= 0 or len(rates) != 1:
                raise ValueError()
            rate = rates[0]
            interval = float(number(rate['intervalNum']) / number(rate['limit'])) * {'SECONDS': 1, 'MINUTES': 60}[rate['measure']]
            if interval <= 0:
                raise ValueError()
            end = int(self._clock() * 1000)
            # Full bounded history read detects old orders finalized after the last
            # sync. Only changed stable IDs are reconciled. Do not assume `from`
            # means lastModified, or rely on current-session /executions for history.
            rows = self._history(0, end, limits[0], interval, self._clock() + 180)
            instruments = self._request(f'/trade/accounts/{self._account["id"]}/instruments')['d']['instruments']
            lookup = {}
            for item in instruments:
                key = identity(item['tradableInstrumentId'])
                if key in lookup:
                    raise ValueError()
                lookup[key] = item
            positions = self._rows('positions', 'positionsConfig')
            mapped = {}
            for row in rows:
                filled = number(row['filledQty'])
                if filled == 0:
                    continue
                instrument = lookup.get(identity(row['tradableInstrumentId']))
                if not instrument:
                    raise BrokerHistoryError('TradeLocker instrument is unknown; no symbol was guessed', category='history')
                execution = Execution(provider=self.provider, environment=self.environment, account_key=self.account_key,
                    external_id='order:' + identity(row['id']), order_id=identity(row['id']),
                    position_id=identity(row['positionId']), symbol=identity(instrument['name']),
                    asset_class=identity(instrument['type']), side=row['side'], quantity=str(filled),
                    price=str(number(row['avgPrice'])), timestamp=utc_millis(row['lastModified']),
                    quantity_unit='provider_quantity', evidence='order_aggregate',
                    metadata={k: row[k] for k in ('createdDate', 'lastModified', 'status', 'tradableInstrumentId', 'routeId', 'isOpen') if k in row})
                if execution.external_id in mapped and mapped[execution.external_id] != execution:
                    raise BrokerHistoryError('TradeLocker history changed during pagination; retry', category='history')
                mapped[execution.external_id] = execution
            return ExecutionBatch(list(mapped.values()), str(end), {identity(p['id']) for p in positions})
        except BrokerHistoryError:
            raise
        except Exception:
            raise BrokerHistoryError('TradeLocker history is incomplete or malformed; previous data retained', category='history') from None
