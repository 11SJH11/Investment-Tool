from __future__ import annotations

from app.data.providers.base import Symbol
from app.storage.database import Database


class SymbolRepository:
    def __init__(self, database: Database):
        self.database = database

    def replace_all(self, symbols: list[Symbol], provider: str) -> int:
        """Synchronise the master list without deleting unchanged security rows.

        Phase 3 tables reference securities by ticker, so DELETE-all/INSERT-all would
        unnecessarily cascade-delete cached fundamentals and price snapshots.
        """
        rows = [_to_row(symbol, provider) for symbol in symbols]
        tickers = [(symbol.ticker.upper(),) for symbol in symbols]
        with self.database.connect() as connection:
            connection.execute("CREATE TEMP TABLE IF NOT EXISTS incoming_securities(ticker TEXT PRIMARY KEY)")
            connection.execute("DELETE FROM incoming_securities")
            connection.executemany("INSERT OR IGNORE INTO incoming_securities(ticker) VALUES (?)", tickers)
            connection.executemany(
                """
                INSERT INTO securities(
                    ticker, name, asset_type, security_type, exchange, status,
                    tradable, fractionable, shortable, provider, provider_id, cik
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    name = excluded.name,
                    asset_type = excluded.asset_type,
                    security_type = excluded.security_type,
                    exchange = COALESCE(excluded.exchange, securities.exchange),
                    status = COALESCE(excluded.status, securities.status),
                    tradable = COALESCE(excluded.tradable, securities.tradable),
                    fractionable = COALESCE(excluded.fractionable, securities.fractionable),
                    shortable = COALESCE(excluded.shortable, securities.shortable),
                    provider = excluded.provider,
                    provider_id = COALESCE(excluded.provider_id, securities.provider_id),
                    cik = COALESCE(excluded.cik, securities.cik),
                    updated_at = CURRENT_TIMESTAMP
                """,
                rows,
            )
            connection.execute(
                "DELETE FROM securities WHERE ticker NOT IN (SELECT ticker FROM incoming_securities)"
            )
        return len(rows)

    def upsert_many(self, symbols: list[Symbol], provider: str) -> int:
        rows = [_to_row(symbol, provider) for symbol in symbols]
        with self.database.connect() as connection:
            connection.executemany(
                """
                INSERT INTO securities(
                    ticker, name, asset_type, security_type, exchange, status,
                    tradable, fractionable, shortable, provider, provider_id, cik
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    name = excluded.name,
                    asset_type = excluded.asset_type,
                    security_type = excluded.security_type,
                    exchange = COALESCE(excluded.exchange, securities.exchange),
                    status = COALESCE(excluded.status, securities.status),
                    tradable = COALESCE(excluded.tradable, securities.tradable),
                    fractionable = COALESCE(excluded.fractionable, securities.fractionable),
                    shortable = COALESCE(excluded.shortable, securities.shortable),
                    provider = excluded.provider,
                    provider_id = COALESCE(excluded.provider_id, securities.provider_id),
                    cik = COALESCE(excluded.cik, securities.cik),
                    updated_at = CURRENT_TIMESTAMP
                """,
                rows,
            )
        return len(rows)

    def apply_cik_map(self, cik_map: dict[str, str]) -> int:
        rows = [(str(cik).zfill(10), ticker.upper()) for ticker, cik in cik_map.items()]
        with self.database.connect() as connection:
            before = connection.total_changes
            connection.executemany(
                "UPDATE securities SET cik = ?, updated_at = CURRENT_TIMESTAMP WHERE ticker = ?",
                rows,
            )
            return connection.total_changes - before

    def cik_map(self) -> dict[str, str]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT ticker, cik FROM securities WHERE cik IS NOT NULL AND cik != ''"
            ).fetchall()
        return {row["ticker"]: row["cik"] for row in rows}

    def count(self) -> int:
        with self.database.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM securities").fetchone()[0])

    def search(self, query: str = "", limit: int = 50, offset: int = 0) -> list[dict]:
        query = query.strip()
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        with self.database.connect() as connection:
            if query:
                like = f"%{query.upper()}%"
                rows = connection.execute(
                    """
                    SELECT * FROM securities
                    WHERE UPPER(ticker) LIKE ? OR UPPER(name) LIKE ?
                    ORDER BY
                        CASE WHEN UPPER(ticker) = ? THEN 0 WHEN UPPER(ticker) LIKE ? THEN 1 ELSE 2 END,
                        ticker
                    LIMIT ? OFFSET ?
                    """,
                    (like, like, query.upper(), f"{query.upper()}%", limit, offset),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM securities ORDER BY ticker LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def get(self, ticker: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM securities WHERE ticker = ?", (ticker.upper(),)
            ).fetchone()
        return _row_to_dict(row) if row else None


def _to_row(symbol: Symbol, provider: str) -> tuple:
    return (
        symbol.ticker.upper(),
        symbol.name,
        symbol.asset_type,
        symbol.security_type,
        symbol.exchange,
        symbol.status,
        _bool_to_int(symbol.tradable),
        _bool_to_int(symbol.fractionable),
        _bool_to_int(symbol.shortable),
        provider,
        symbol.provider_id,
        symbol.cik,
    )


def _bool_to_int(value: bool | None) -> int | None:
    return int(value) if value is not None else None


def _row_to_dict(row) -> dict:
    result = dict(row)
    for key in ("tradable", "fractionable", "shortable"):
        if result[key] is not None:
            result[key] = bool(result[key])
    return result
