"""Explicit read-only sync dispatch. Credentials stay in backend profile objects."""
from threading import Lock
from types import SimpleNamespace
from hashlib import sha256
import json
import sqlite3

from app.brokers.base import BrokerHistoryError
from app.brokers.oanda import OandaHistory
from app.brokers.profiles import profiles
from app.brokers.trading212 import Trading212Portfolio
from app.brokers.tradovate import TradovateHistory
from app.brokers.tradelocker import TradeLockerHistory
from app.brokers.metatrader5 import MetaTrader5History
from app.services.execution_sync import reconcile
from app.services.broker_sync import BrokerSyncService
from app.storage.broker_sync_repository import BrokerSyncRepository
from app.storage.portfolio_broker_repository import PortfolioBrokerRepository


ADAPTERS = {"oanda": OandaHistory, "trading212": Trading212Portfolio, "tradovate": TradovateHistory}
ADAPTERS['tradelocker'] = TradeLockerHistory
ADAPTERS['mt5'] = MetaTrader5History
CAPABILITIES = {
    "oanda": {"provider": "oanda", "destination": "journal", "read_only": True, "supported": True, "closed_trades": True, "execution": False},
    "trading212": Trading212Portfolio.capability_report(),
    "tradovate": TradovateHistory.capability_report(),
    "tradelocker": TradeLockerHistory.capability_report(),
    "mt5": MetaTrader5History.capability_report(),
}


class BrokerConnections:
    def __init__(self, settings, database, *, factories=None, legacy_oanda=None):
        self.database = database
        self.profiles = {p.id: p for p in profiles(settings)}
        self.factories = {**ADAPTERS, **(factories or {})}
        self.portfolio = PortfolioBrokerRepository(database)
        self.state = BrokerSyncRepository(database)
        self._lock = Lock()
        self._profile_locks = {key: Lock() for key in self.profiles}
        for p in self.profiles.values():
            saved = json.loads(self._setting('broker_connection:' + p.id) or '{}')
            if 'disconnected' in saved:
                p.enabled = not saved['disconnected']
            if p.provider in {'tradelocker', 'mt5', 'trading212'} and saved.get('environment') in {'demo', 'live'}:
                p.environment = saved['environment']
        self._oanda = {}
        for p in self.profiles.values():
            if p.provider == "oanda":
                config = SimpleNamespace(oanda_access_token=p.credentials.get('token',''),
                    oanda_account_id=p.credentials.get('account_id',''), oanda_environment=p.environment,
                    oanda_journal_configured=p.configured)
                self._oanda[p.id] = legacy_oanda if p.id == 'oanda-default' and legacy_oanda else BrokerSyncService(config, database, self.factories['oanda'])

    def _setting(self, key):
        # Unconfigured status remains usable before application initialization.
        if not self.database.path.exists():
            return None
        try:
            return self.database.get_setting(key)
        except sqlite3.OperationalError as exc:
            if str(exc) == 'no such table: app_settings':
                return None
            raise

    def _profile(self, profile_id):
        if profile_id not in self.profiles:
            raise BrokerHistoryError("Unknown broker profile")
        return self.profiles[profile_id]

    def status(self, profile_id):
        p = self._profile(profile_id)
        status = {**CAPABILITIES[p.provider], "profile_id": p.id, "environment": p.environment,
                  "configured": p.configured, "status": "never_synced" if p.configured else "not_configured"}
        saved = json.loads(self._setting('broker_connection:' + p.id) or '{}')
        status['disconnected'] = bool(saved.get('disconnected'))
        status['error_category'] = self._setting('broker_error_category:' + p.id)
        if status['disconnected']:
            status['status'] = 'disconnected'
        if not p.configured:
            return status
        if p.provider in {'tradelocker', 'mt5'}:
            key = self._setting(self._selection(p))
            if key:
                state = self.state.state(p.provider, key)
                status.update({k: state.get(k) for k in ('last_success_at', 'error')})
                status.update(account_key=key, account=f'{p.provider.upper()} {p.environment} / {key[:8]}', status=state.get('status', 'never_synced'))
            status['error_category'] = self._setting('broker_error_category:' + p.id)
            return status
        if p.provider == 'tradovate':
            if p.configured: status['status'] = 'unsupported'
        elif p.provider == 'oanda':
            status.update(self._oanda[p.id].status())
        else:
            # Profile binding stores only the opaque verified account key. No API
            # call is made by status/Settings/page load, even when configured.
            key = self._setting(self._binding(p))
            if key:
                saved = self.state.state(p.provider, key)
                status.update({k: saved.get(k) for k in ('last_success_at','error')})
                status['last_account_key'] = key
                if p.configured: status['status'] = saved.get('status','never_synced')
        return status

    @staticmethod
    def _binding(p):
        identity = sha256(f"{p.provider}:{p.environment}:{p.credentials.get('api_key','')}".encode()).hexdigest()
        return 'broker_profile:' + p.id + ':' + identity

    def statuses(self):
        return {"items": [self.status(key) for key in self.profiles]}

    def sync(self, profile_id):
        self._profile(profile_id)
        lock = self._profile_locks[profile_id]
        if not lock.acquire(blocking=False):
            raise BrokerHistoryError('A broker operation is already running for this profile', category='busy')
        try:
            return self._sync(profile_id)
        finally:
            lock.release()

    def _sync(self, profile_id):
        p = self._profile(profile_id)
        if not p.configured or not CAPABILITIES[p.provider]['supported']:
            return self.status(profile_id)
        if p.provider == 'oanda':
            return self._oanda[p.id].sync()
        if p.provider in {'tradelocker', 'mt5'}:
            return self._history_sync(p)
        if not self._lock.acquire(blocking=False):
            raise BrokerHistoryError("A Portfolio broker sync is already running")
        adapter = None
        try:
            adapter = self.factories[p.provider](p.credentials['api_key'],p.credentials['api_secret'],p.environment)
            summary = adapter.read_account()
            cursor = self.state.state(adapter.provider,adapter.account_key).get('cursor')
            result = self.portfolio.commit(adapter,adapter.fetch_snapshot(summary),cursor,self._binding(p))
            self.database.set_setting('broker_error_category:' + p.id, '')
            return result
        except Exception as exc:
            message = str(exc) if isinstance(exc,BrokerHistoryError) else "Broker sync could not complete; previous Portfolio records were preserved"
            self.database.set_setting('broker_error_category:' + p.id, getattr(exc, 'category', 'provider'))
            if adapter and adapter.account_key:
                self.state.failure(adapter,message)
            raise BrokerHistoryError(message, status_code=getattr(exc,'status_code',None), retry_after=getattr(exc,'retry_after',None)) from None
        finally:
            if adapter: adapter.close()
            self._lock.release()

    def discover(self, profile_id):
        p = self._profile(profile_id)
        lock = self._profile_locks[profile_id]
        if not lock.acquire(blocking=False):
            raise BrokerHistoryError('A broker operation is already running for this profile', category='busy')
        try:
            return self._discover(p)
        finally:
            lock.release()

    def _discover(self, p):
        if p.provider not in {'tradelocker', 'mt5', 'trading212'} or not p.configured:
            raise BrokerHistoryError('Account discovery is unavailable for this profile', category='configuration')
        adapter = None
        try:
            if p.provider == 'trading212':
                adapter = self.factories[p.provider](p.credentials['api_key'], p.credentials['api_secret'], p.environment)
                adapter.read_account()
            else:
                adapter = self.factories[p.provider](p.credentials, p.environment)
            return {'items': adapter.accounts(), 'status': 'connected'}
        except Exception as exc:
            self._history_error(p, exc)
        finally:
            if adapter:
                adapter.close()

    def select_account(self, profile_id, selected_key):
        # Verify against provider discovery, never accept a client supplied account ID.
        p = self._profile(profile_id)
        lock = self._profile_locks[profile_id]
        if not lock.acquire(blocking=False):
            raise BrokerHistoryError('A broker operation is already running for this profile', category='busy')
        try:
            discovered = self._discover(p)
            if selected_key not in {a['account_key'] for a in discovered['items']}:
                raise BrokerHistoryError('Account is not available on this connection', category='configuration')
            self.database.set_setting(self._selection(p), selected_key)
            return self.status(profile_id)
        finally:
            lock.release()

    def _history_error(self, p, exc, adapter=None):
        category = exc.category if isinstance(exc, BrokerHistoryError) else 'provider'
        message = str(exc) if isinstance(exc, BrokerHistoryError) else 'Broker history could not be reconciled; previous data retained'
        self.database.set_setting('broker_error_category:' + p.id, category)
        if adapter and adapter.account_key:
            self.state.failure(adapter, message)
        raise BrokerHistoryError(message, category=category, status_code=getattr(exc, 'status_code', None),
                                 retry_after=getattr(exc, 'retry_after', None)) from None

    def _history_sync(self, p):
        adapter = None
        try:
            adapter = self.factories[p.provider](p.credentials, p.environment)
            selected = self._setting(self._selection(p))
            adapter.connect(selected)
            result = reconcile(adapter, self.database)
            self.database.set_setting(self._selection(p), adapter.account_key)
            self.database.set_setting('broker_error_category:' + p.id, '')
            return result
        except Exception as exc:
            self._history_error(p, exc, adapter)
        finally:
            if adapter:
                adapter.close()

    @staticmethod
    def _selection(p):
        scope = sha256(json.dumps([p.environment, p.credentials.get('server', '')]).encode()).hexdigest()
        return 'broker_selection:' + p.id + ':' + scope

    def configure_connection(self, profile_id, enabled, environment):
        p = self._profile(profile_id)
        if p.provider not in {'tradelocker', 'mt5', 'trading212'} or environment not in {'demo', 'live'}:
            raise BrokerHistoryError('Unsupported broker connection configuration', category='configuration')
        lock = self._profile_locks[profile_id]
        if not lock.acquire(blocking=False):
            raise BrokerHistoryError('Wait for the active broker operation before changing connection', category='busy')
        try:
            p.enabled, p.environment = enabled, environment
            self.database.set_setting('broker_connection:' + p.id, json.dumps(dict(disconnected=not enabled, environment=environment)))
            return self.status(profile_id)
        finally:
            lock.release()
