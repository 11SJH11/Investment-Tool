"""Durable job control only; OHLCV remains in the canonical market store."""
import json


class MarketWarmupRepository:
    def __init__(self, database):
        self.database = database
        with database.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS market_warmup_jobs (
                id TEXT PRIMARY KEY, document TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")

    def save(self, job):
        with self.database.connect() as db:
            db.execute("""INSERT INTO market_warmup_jobs(id, document) VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET document=excluded.document, updated_at=CURRENT_TIMESTAMP""",
                (job['id'], json.dumps(job)))

    def list(self):
        with self.database.connect() as db:
            rows = db.execute('SELECT document FROM market_warmup_jobs ORDER BY updated_at DESC').fetchall()
        return [json.loads(row['document']) for row in rows]
