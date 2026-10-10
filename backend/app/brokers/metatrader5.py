"""Optional official MetaTrader5 Python integration. No order APIs are called.

The native package has process-global terminal/account state. Hold one lock for
the complete connection/read/shutdown lifecycle, including multiple profiles.
"""
from datetime import datetime, timezone
import importlib
import logging
from threading import Lock
import time

from app.brokers.base import BrokerHistoryError
from app.brokers.executions import Execution, ExecutionBatch, account_key, identity, number, utc_millis

_terminal_lock = Lock()


class MetaTrader5History:
    provider = 'mt5'

    def __init__(self, credentials, environment, *, module=None, clock=time.time):
        if environment not in {'demo', 'live'}:
            raise BrokerHistoryError('MetaTrader 5 environment must be demo or live', category='configuration')
        self.environment, self._credentials = environment, dict(credentials)
        self._module, self._clock = module, clock
        self._locked = self._initialized = False
        self.account_key = self.account_label = self.currency = None

    @staticmethod
    def capability_report():
        return dict(provider='mt5', destination='journal', supported=True, read_only=True,
            execution=False, closed_trades=True, account_discovery=True,
            reason='Requires the official MetaTrader5 Python package and a local MetaTrader 5 terminal logged in on the backend machine. MT4 is not supported.')

    def close(self):
        try:
            if self._initialized:
                self._module.shutdown()  # closes Python IPC, not the terminal
        except Exception:
            # Cleanup cannot retroactively turn a committed import into a failed
            # one. Do not log native exception strings/last_error credentials.
            logging.getLogger(__name__).warning('MetaTrader 5 IPC disconnect failed')
        finally:
            self._initialized = False
            self._credentials.clear()
            if self._locked:
                self._locked = False
                _terminal_lock.release()

    def _start(self):
        if self._initialized:
            return
        if not _terminal_lock.acquire(blocking=False):
            raise BrokerHistoryError('MetaTrader 5 terminal is busy with another sync', category='busy')
        self._locked = True
        try:
            if self._module is None:
                try:
                    self._module = importlib.import_module('MetaTrader5')
                except ImportError:
                    raise BrokerHistoryError('Install the optional official MetaTrader5 package on the backend machine', category='configuration') from None
            options = {'timeout': 30000}
            if self._credentials.get('login'):
                options['login'] = int(self._credentials['login'])
            if self._credentials.get('password'):
                options['password'] = self._credentials['password']
            if self._credentials.get('server'):
                options['server'] = self._credentials['server']
            path = self._credentials.get('terminal_path')
            args = [path] if path else []
            if not self._module.initialize(*args, **options):
                raise BrokerHistoryError('MetaTrader 5 could not connect; check the local terminal and login', category='connection')
            self._initialized = True
        except BrokerHistoryError:
            self.close()
            raise
        except Exception:
            self.close()
            raise BrokerHistoryError('MetaTrader 5 connection failed; check local terminal settings', category='connection') from None

    def _account(self):
        info = self._module.account_info()
        if info is None:
            raise BrokerHistoryError('MetaTrader 5 account is unavailable', category='connection')
        environment = {0: 'demo', 2: 'live'}.get(info.trade_mode)
        if environment != self.environment:
            raise BrokerHistoryError('MetaTrader 5 account environment does not match this profile', category='configuration')
        if self._credentials.get('login') and identity(info.login) != self._credentials['login']:
            raise BrokerHistoryError('MetaTrader 5 connected to a different account', category='configuration')
        if self._credentials.get('server') and info.server != self._credentials['server']:
            raise BrokerHistoryError('MetaTrader 5 connected to a different server', category='configuration')
        key = account_key(self.provider, environment, identity(info.server), info.login)
        return info, key

    def accounts(self):
        self._start()
        try:
            info, key = self._account()
            return [dict(account_key=key, environment=self.environment,
                         label=f'MetaTrader 5 {self.environment} / {key[:8]}', currency=info.currency)]
        except BrokerHistoryError:
            raise
        except Exception:
            raise BrokerHistoryError('MetaTrader 5 account discovery failed', category='connection') from None

    def connect(self, selected_key=None):
        selected = self.accounts()[0]
        if selected_key and selected_key != selected['account_key']:
            raise BrokerHistoryError('The selected MetaTrader 5 account is no longer connected', category='configuration')
        self.account_key, self.account_label, self.currency = selected['account_key'], selected['label'], selected['currency']
        return selected

    def read_executions(self, cursor):
        try:
            start = max(0, int(cursor or 0) - 86400000)  # overlap late postings/reconnect
            end = int(self._clock() * 1000)
            if end < start:
                raise ValueError()
            deals = self._module.history_deals_get(datetime.fromtimestamp(start / 1000, timezone.utc),
                                                   datetime.fromtimestamp(end / 1000, timezone.utc))
            if deals is None or len(deals) > 100000:
                raise BrokerHistoryError('MetaTrader 5 history is unavailable or exceeds the safe sync budget', category='history')
            position_ids = {d.position_id for d in deals if d.position_id}
            mapped = {}
            for position_id in sorted(position_ids):
                # Retrieve complete position history even if the opening is older
                # than the incremental cursor. Deal tickets deduplicate overlap.
                history = self._module.history_deals_get(position=int(position_id))
                if history is None or len(history) > 100000 or len(mapped) + len(history) > 100000:
                    raise BrokerHistoryError('MetaTrader 5 position history is unavailable or too large', category='history')
                for deal in history:
                    if deal.type not in (0, 1):
                        if any(number(getattr(deal, name, 0)) != 0 for name in ('profit', 'commission', 'swap', 'fee')):
                            raise BrokerHistoryError('MetaTrader 5 position has separate cash adjustments requiring reconciliation', category='history')
                        continue
                    if deal.position_id != position_id or deal.entry not in (0, 1, 3):
                        raise BrokerHistoryError('MetaTrader 5 reversal or unsupported position history requires reconciliation', category='history')
                    stamp = getattr(deal, 'time_msc', deal.time * 1000)
                    if stamp > end:
                        raise BrokerHistoryError('MetaTrader 5 history changed during sync; retry', category='history')
                    symbol = self._module.symbol_info(deal.symbol)
                    if symbol is None or getattr(symbol, 'name', None) != deal.symbol:
                        raise BrokerHistoryError('MetaTrader 5 symbol is unknown; mapping was not guessed', category='history')
                    money = lambda name: str(number(getattr(deal, name))) if getattr(deal, name, None) is not None else None
                    e = Execution(provider=self.provider, environment=self.environment, account_key=self.account_key,
                        external_id=identity(deal.ticket), order_id=identity(deal.order), position_id=identity(position_id),
                        symbol=identity(deal.symbol), asset_class='broker_instrument', side='buy' if deal.type == 0 else 'sell',
                        quantity=str(number(deal.volume)), price=str(number(deal.price)), timestamp=utc_millis(stamp),
                        quantity_unit='lots', role='entry' if deal.entry == 0 else 'exit',
                        commission=money('commission'), swap=money('swap'), fee=money('fee'), realized_pnl=money('profit'),
                        metadata=dict(deal_entry=deal.entry, deal_type=deal.type,
                            deal_reason=getattr(deal,'reason',None),
                            programmatic_order=(getattr(deal,'reason',None)==getattr(self._module,'DEAL_REASON_EXPERT',object())),
                            current_contract_size=str(number(symbol.trade_contract_size)),
                            contract_size_basis='current_symbol_info_not_historical',
                            cost_scope='position_deals_only; unallocated account charges are not allocated',
                            profit_currency=getattr(symbol, 'currency_profit', None)))
                    if e.external_id in mapped and mapped[e.external_id] != e:
                        raise BrokerHistoryError('MetaTrader 5 returned conflicting deal tickets', category='history')
                    mapped[e.external_id] = e
            positions = self._module.positions_get()
            if positions is None:
                raise BrokerHistoryError('MetaTrader 5 open positions are unavailable', category='history')
            if self._account()[1] != self.account_key:
                raise BrokerHistoryError('MetaTrader 5 account changed during sync; previous data retained', category='connection')
            return ExecutionBatch(list(mapped.values()), str(end), {identity(p.identifier) for p in positions})
        except BrokerHistoryError:
            raise
        except Exception:
            raise BrokerHistoryError('MetaTrader 5 history could not be read; previous data retained', category='history') from None
