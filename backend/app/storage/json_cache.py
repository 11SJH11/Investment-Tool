from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from app.storage.database import Database


class JsonCacheRepository:
    def __init__(self, database: Database):
        self.database = database

    def get(self, namespace: str, key: str) -> Any | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT payload, expires_at FROM json_cache WHERE namespace = ? AND cache_key = ?",
                (namespace, key),
            ).fetchone()
        if not row:
            return None
        if _parse(row["expires_at"]) <= datetime.now(timezone.utc):
            self.delete(namespace, key)
            return None
        return json.loads(row["payload"])

    def set(self, namespace: str, key: str, payload: Any, ttl_seconds: int) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(0, ttl_seconds))
        encoded = json.dumps(payload, separators=(",", ":"), allow_nan=False)
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO json_cache(namespace, cache_key, payload, expires_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(namespace, cache_key) DO UPDATE SET
                    payload = excluded.payload,
                    expires_at = excluded.expires_at,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (namespace, key, encoded, expires_at.isoformat()),
            )

    def delete(self, namespace: str, key: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM json_cache WHERE namespace = ? AND cache_key = ?",
                (namespace, key),
            )


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
