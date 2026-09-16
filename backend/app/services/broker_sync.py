from threading import Lock

from app.brokers.base import BrokerHistoryError
from app.brokers.oanda import OandaHistory
from app.storage.broker_sync_repository import BrokerSyncRepository


class BrokerSyncService:
    def __init__(self, settings, database, factory=OandaHistory):
        self.settings = settings
        self.repository = BrokerSyncRepository(database)
        self.factory = factory
        self._lock = Lock()

    def _adapter(self):
        return self.factory(self.settings.oanda_access_token.strip(), self.settings.oanda_account_id.strip(), self.settings.oanda_environment.strip().lower())

    def status(self):
        if not self.settings.oanda_journal_configured:
            return {"provider": "oanda", "configured": False, "status": "not_configured", "label": "Not configured", "read_only": True}
        adapter = self._adapter()
        try:
            state = self.repository.state(adapter.provider, adapter.account_key)
            return {"provider": "oanda", "configured": True, "read_only": True, "account": adapter.account_label,
                    "environment": adapter.environment, "status": state.get("status", "never_synced"),
                    "last_success_at": state.get("last_success_at"), "error": state.get("error")}
        finally:
            adapter.close()

    def sync(self):
        if not self.settings.oanda_journal_configured:
            return self.status()
        if not self._lock.acquire(blocking=False):
            raise BrokerHistoryError("A broker sync is already running")
        adapter = None
        try:
            adapter = self._adapter()
            cursor = self.repository.state(adapter.provider, adapter.account_key).get("cursor")
            batch = adapter.fetch_closed(cursor)
            result = self.repository.commit(adapter, batch, cursor)
            return {"status": "success", **result}
        except Exception as exc:
            message = str(exc) if isinstance(exc, BrokerHistoryError) else "Broker sync could not complete; previous trades and cursor were preserved. Retry after checking the connection."
            if adapter:
                self.repository.failure(adapter, message)
            raise BrokerHistoryError(message) from None
        finally:
            if adapter:
                adapter.close()
            self._lock.release()
