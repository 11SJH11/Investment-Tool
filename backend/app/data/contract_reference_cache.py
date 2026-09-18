"""Durable, separate futures reference cache with process-wide single flight."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from threading import Lock
import time

from app.data.http import ProviderHttpError

_guard = Lock()
_locks = {}


class ContractReferenceCache:
    def __init__(self, path=None, *, ttl=86400, stale_ttl=30*86400, clock=time.time):
        self.path = Path(path) if path else None
        self.ttl, self.stale_ttl, self.clock = ttl, stale_ttl, clock
        self.memory = {}
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.connection() as db:
                db.execute("CREATE TABLE IF NOT EXISTS contract_reference (key TEXT PRIMARY KEY, payload TEXT, fetched REAL, retry_until REAL NOT NULL DEFAULT 0)")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.row_factory = sqlite3.Row
            with db:
                yield db
        finally:
            db.close()

    def _read(self, key):
        if not self.path:
            return self.memory.get(key)
        with self.connection() as db:
            row = db.execute("SELECT * FROM contract_reference WHERE key=?", (key,)).fetchone()
        return dict(row) if row else None

    def _write(self, key, payload, fetched, retry_until=0):
        row = dict(key=key, payload=payload, fetched=fetched, retry_until=retry_until)
        if not self.path:
            self.memory[key] = row
            return
        with self.connection() as db:
            db.execute("INSERT INTO contract_reference VALUES (:key,:payload,:fetched,:retry_until) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,fetched=excluded.fetched,retry_until=excluded.retry_until", row)

    def get(self, key, load, *, refresh=False):
        observed = self._read(key)
        lock_key = (str(self.path.resolve()) if self.path else id(self), key)
        with _guard:
            lock = _locks.setdefault(lock_key, Lock())
        with lock:
            row = self._read(key)
            now = self.clock()
            usable = bool(row and row["payload"] and now-row["fetched"] <= self.stale_ttl)
            fresh = usable and now-row["fetched"] < self.ttl
            # Concurrent explicit refreshes share the first successful request.
            updated = row and (not observed or row["fetched"] != observed["fetched"])
            if fresh and (not refresh or updated):
                return json.loads(row["payload"])
            if row and row["retry_until"] > now:
                if usable:
                    return json.loads(row["payload"])
                raise ProviderHttpError("Massive contract reference is rate-limited; no usable cached metadata. Retry after the provider cooldown.", status_code=429, retry_after=row["retry_until"]-now)
            try:
                payload = load()
            except ProviderHttpError as exc:
                if exc.status_code != 429 and "HTTP 429" not in str(exc):
                    raise
                cooldown = max(60, exc.retry_after or 0)
                self._write(key, row["payload"] if row else None, row["fetched"] if row else None, now+cooldown)
                if usable:
                    return json.loads(row["payload"])
                raise ProviderHttpError("Massive contract reference is rate-limited (HTTP 429); no usable cached metadata. Retry after the provider cooldown.", status_code=429, retry_after=cooldown) from None
            encoded = json.dumps(payload, allow_nan=False, separators=(",", ":"))
            self._write(key, encoded, now)
            return payload
