"""Explicit read-only sync dispatch. Credentials stay in backend profile objects."""
from threading import Lock
from types import SimpleNamespace
from hashlib import sha256

from app.brokers.base import BrokerHistoryError
from app.brokers.oanda import OandaHistory
from app.brokers.profiles import profiles
from app.brokers.trading212 import Trading212Portfolio
from app.brokers.tradovate import TradovateHistory
from app.services.broker_sync import BrokerSyncService
from app.storage.broker_sync_repository import BrokerSyncRepository
from app.storage.portfolio_broker_repository import PortfolioBrokerRepository


ADAPTERS = {"oanda": OandaHistory, "trading212": Trading212Portfolio, "tradovate": TradovateHistory}
CAPABILITIES = {
    "oanda": {"provider": "oanda", "destination": "journal", "read_only": True, "supported": True, "closed_trades": True, "execution": False},
    "trading212": Trading212Portfolio.capability_report(),
    "tradovate": TradovateHistory.capability_report(),
}


class BrokerConnections:
    def __init__(self, settings, database, *, factories=None, legacy_oanda=None):
        self.database = database
        self.profiles = {p.id: p for p in profiles(settings)}
        self.factories = {**ADAPTERS, **(factories or {})}
        self.portfolio = PortfolioBrokerRepository(database)
        self.state = BrokerSyncRepository(database)
        self._lock = Lock()
        self._oanda = {}
        for p in self.profiles.values():
            if p.provider == "oanda":
                config = SimpleNamespace(oanda_access_token=p.credentials.get('token',''),
                    oanda_account_id=p.credentials.get('account_id',''), oanda_environment=p.environment,
                    oanda_journal_configured=p.configured)
                self._oanda[p.id] = legacy_oanda if p.id == 'oanda-default' and legacy_oanda else BrokerSyncService(config, database, self.factories['oanda'])

    def _profile(self, profile_id):
        if profile_id not in self.profiles:
            raise BrokerHistoryError("Unknown broker profile")
        return self.profiles[profile_id]

    def status(self, profile_id):
        p = self._profile(profile_id)
        status = {**CAPABILITIES[p.provider], "profile_id": p.id, "environment": p.environment,
                  "configured": p.configured, "status": "never_synced" if p.configured else "not_configured"}
        if not p.configured:
            return status
        if p.provider == 'tradovate':
            if p.configured: status['status'] = 'unsupported'
        elif p.provider == 'oanda':
            status.update(self._oanda[p.id].status())
        else:
            # Profile binding stores only the opaque verified account key. No API
            # call is made by status/Settings/page load, even when configured.
            key = self.database.get_setting(self._binding(p))
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
        p = self._profile(profile_id)
        if not p.configured or not CAPABILITIES[p.provider]['supported']:
            return self.status(profile_id)
        if p.provider == 'oanda':
            return self._oanda[p.id].sync()
        if not self._lock.acquire(blocking=False):
            raise BrokerHistoryError("A Portfolio broker sync is already running")
        adapter = None
        try:
            adapter = self.factories[p.provider](p.credentials['api_key'],p.credentials['api_secret'],p.environment)
            summary = adapter.read_account()
            cursor = self.state.state(adapter.provider,adapter.account_key).get('cursor')
            result = self.portfolio.commit(adapter,adapter.fetch_snapshot(summary),cursor,self._binding(p))
            return result
        except Exception as exc:
            message = str(exc) if isinstance(exc,BrokerHistoryError) else "Broker sync could not complete; previous Portfolio records were preserved"
            if adapter and adapter.account_key:
                self.state.failure(adapter,message)
            raise BrokerHistoryError(message) from None
        finally:
            if adapter: adapter.close()
            self._lock.release()
