from __future__ import annotations

from app.data.providers.base import SecurityMasterProvider
from app.data.providers.sec import SecProvider
from app.storage.symbol_repository import SymbolRepository


class SymbolUniverseService:
    def __init__(
        self,
        repository: SymbolRepository,
        security_master: SecurityMasterProvider,
        sec_provider: SecProvider | None = None,
    ):
        self.repository = repository
        self.security_master = security_master
        self.sec_provider = sec_provider

    def refresh(self) -> dict:
        existing_ciks = self.repository.cik_map()
        symbols = self.security_master.list_symbols()
        count = self.repository.replace_all(symbols, self.security_master.key)
        if existing_ciks:
            self.repository.apply_cik_map(existing_ciks)
        cik_matches = 0
        if self.sec_provider and self.sec_provider is not self.security_master:
            cik_matches = self.repository.apply_cik_map(self.sec_provider.cik_map())
        return {
            "source": self.security_master.key,
            "symbols": count,
            "cik_matches": cik_matches,
        }
