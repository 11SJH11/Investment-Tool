from __future__ import annotations

from datetime import datetime, timezone

from app.storage.database import Database


class MarketCacheRepository:
    def __init__(self, database: Database):
        self.database = database

    def get(self, namespace: str, ticker: str, timeframe: str) -> tuple[datetime, datetime] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT covered_start, covered_end
                FROM market_cache_coverage
                WHERE namespace = ? AND ticker = ? AND timeframe = ?
                """,
                (namespace, ticker.upper(), timeframe),
            ).fetchone()
        if not row:
            return None
        return (_parse(row["covered_start"]), _parse(row["covered_end"]))

    def extend(self, namespace: str, ticker: str, timeframe: str, start: datetime, end: datetime) -> None:
        start = _utc(start)
        end = _utc(end)
        current = self.get(namespace, ticker, timeframe)
        if current:
            start = min(start, current[0])
            end = max(end, current[1])
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO market_cache_coverage(namespace, ticker, timeframe, covered_start, covered_end)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(namespace, ticker, timeframe) DO UPDATE SET
                    covered_start = excluded.covered_start,
                    covered_end = excluded.covered_end,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (namespace, ticker.upper(), timeframe, start.isoformat(), end.isoformat()),
            )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse(value: str) -> datetime:
    return _utc(datetime.fromisoformat(value))
