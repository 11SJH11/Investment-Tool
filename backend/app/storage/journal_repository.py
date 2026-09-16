from __future__ import annotations

import json
from app.core import journal_analytics as analysis
from typing import Any

from app.storage.database import Database


TRADE_COLUMNS = (
    "source", "name", "account", "ticker", "direction", "status", "opened_at", "closed_at",
    "entry_price", "exit_price", "quantity", "position_amount", "position_currency", "stop_loss", "take_profit", "fees", "result",
    "result_source", "pnl_amount", "pnl_pct", "r_multiple", "planned_rr", "pnl_override", "override_reason", "pnl_source", "trade_type", "setup", "market_condition",
    "entry_timeframe", "timeframe_alignment", "dxy", "session_time", "tf_type", "wick", "analysis",
    "entry_notes", "management", "learning", "notes", "timeframe_notes",
    "external_provider", "external_id", "external_order_id", "source_metadata", "imported_at",
    "playbook_id", "setup_grade", "plan_followed", "review_data", "external_account_key", "account_currency",
    "broker_realized_pnl", "financing", "commission", "guaranteed_execution_fee", "dividend_adjustment",
    "initial_risk_amount", "risk_source", "costs_complete",
)


class JournalRepository:
    def __init__(self, database: Database):
        self.database = database

    def create_trade(self, payload: dict[str, Any]) -> dict:
        values = [_encode(payload.get(column), column) for column in TRADE_COLUMNS]
        placeholders = ",".join("?" for _ in TRADE_COLUMNS)
        with self.database.connect() as connection:
            cursor = connection.execute(
                f"INSERT INTO journal_trades({','.join(TRADE_COLUMNS)}) VALUES ({placeholders})",
                values,
            )
            row = connection.execute("SELECT * FROM journal_trades WHERE id=?", (cursor.lastrowid,)).fetchone()
        return _trade(row)

    def get_by_external(self, *, source: str, external_provider: str, external_id: str) -> dict | None:
        if not external_id:
            return None
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM journal_trades WHERE source=? AND external_provider=? AND external_id=?",
                (source, external_provider or "", external_id),
            ).fetchone()
        return _trade(row) if row else None

    def update_trade(self, trade_id: int, payload: dict[str, Any]) -> dict | None:
        fields = [column for column in TRADE_COLUMNS if column in payload]
        if not fields:
            return self.get_trade(trade_id)
        values = [_encode(payload.get(column), column) for column in fields]
        with self.database.connect() as connection:
            connection.execute(
                f"UPDATE journal_trades SET {','.join(f'{field}=?' for field in fields)}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (*values, trade_id),
            )
            row = connection.execute("SELECT * FROM journal_trades WHERE id=?", (trade_id,)).fetchone()
        return _trade(row) if row else None

    def get_trade(self, trade_id: int) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM journal_trades WHERE id=?", (trade_id,)).fetchone()
        return _trade(row) if row else None

    def list_trades(self, *, source: str | None = None, ticker: str | None = None, limit: int = 500) -> list[dict]:
        where, params = [], []
        if source:
            where.append("source=?")
            params.append(source)
        if ticker:
            where.append("UPPER(ticker)=?")
            params.append(ticker.upper())
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        with self.database.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM journal_trades {clause} ORDER BY COALESCE(opened_at, created_at) DESC, id DESC LIMIT ?",
                (*params, max(1, min(limit, 5000))),
            ).fetchall()
        return [_trade(row) for row in rows]

    def delete_trade(self, trade_id: int) -> bool:
        with self.database.connect() as connection:
            connection.execute("DELETE FROM media_attachments WHERE owner_type='trade' AND owner_id=?", (trade_id,))
            cursor = connection.execute("DELETE FROM journal_trades WHERE id=?", (trade_id,))
        return cursor.rowcount > 0


    def filters(self, filters=None):
        result = dict(filters or {})
        result["timezone"] = result.get("timezone") or self.database.get_setting("journal_timezone") or "UTC"
        analysis.journal_zone(result["timezone"])
        return result

    def filtered_trades(self, filters=None):
        filters = self.filters(filters)
        with self.database.connect() as connection:
            rows = connection.execute("SELECT t.*, p.title AS playbook_title FROM journal_trades t LEFT JOIN playbook_entries p ON p.id=t.playbook_id ORDER BY COALESCE(t.opened_at,t.created_at) DESC,t.id DESC").fetchall()
        return analysis.filter_trades([_trade(row) for row in rows], filters)

    def report(self, filters=None):
        filters = self.filters(filters)
        return analysis.report(self.filtered_trades(filters), filters)

    def calendar(self, month=None, source=None, filters=None):
        filters = self.filters({**(filters or {}), **({"source": source} if source else {})})
        buckets = {}
        for t in self.filtered_trades(filters):
            day = t["journal_date"]
            if day and (not month or day.startswith(month + "-")):
                buckets.setdefault(day, []).append(t)
        result = []
        for day, rows in sorted(buckets.items()):
            totals = analysis.summary(rows)
            result.append({"day": day, **totals, "pnl_amount": totals["total_pnl"], "r_total": totals["total_r"]})
        return result

    def analytics(self, source=None, filters=None):
        filters = {**(filters or {}), **({"source": source} if source else {})}
        result = self.report(filters)
        return {**result["summary"], "by_source": result["breakdowns"]["source"], "by_setup": result["breakdowns"]["setup"]}

    def daily(self, review_date, account="Main", filters=None):
        filters = {**(filters or {}), "account": account, "date_from": review_date, "date_to": review_date}
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM daily_reviews WHERE review_date=? AND account=?", (review_date, account)).fetchone()
        return {"review": dict(row) if row else None, "summary": analysis.daily_summary(self.filtered_trades(filters)), "timezone": self.filters(filters)["timezone"], "date_basis": "entry"}

    def upsert_daily_review(self, payload: dict[str, Any]) -> dict:
        columns = (
            "review_date", "account", "focus_goal", "market_condition", "emotional_state", "process",
            "pair", "session", "setups", "learnings", "psychology", "mistakes", "did_well", "improve",
            "actionable_steps", "thoughts",
        )
        values = [payload.get(c) or ("Main" if c == "account" else "") for c in columns]
        with self.database.connect() as connection:
            connection.execute(
                f"""
                INSERT INTO daily_reviews({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})
                ON CONFLICT(review_date,account) DO UPDATE SET
                  {','.join(f'{c}=excluded.{c}' for c in columns if c not in {'review_date','account'})},
                  updated_at=CURRENT_TIMESTAMP
                """,
                values,
            )
            row = connection.execute(
                "SELECT * FROM daily_reviews WHERE review_date=? AND account=?", (values[0], values[1])
            ).fetchone()
        return dict(row)

    def list_daily_reviews(self, limit: int = 120) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM daily_reviews ORDER BY review_date DESC, id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def create_playbook(self, payload: dict[str, Any]) -> dict:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO playbook_entries(title,category,description,rules,checklist,notes,sections,review_fields) VALUES (?,?,?,?,?,?,?,?)",
                (payload["title"], payload.get("category") or "Entry Model", payload.get("description") or "", payload.get("rules") or "", payload.get("checklist") or "", payload.get("notes") or "", json.dumps(payload.get("sections") or {}), json.dumps(payload.get("review_fields") or [])),
            )
            row = connection.execute("SELECT * FROM playbook_entries WHERE id=?", (cursor.lastrowid,)).fetchone()
        return _playbook(row)

    def list_playbook(self) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM playbook_entries ORDER BY category,title").fetchall()
        return [_playbook(row) for row in rows]

    def update_playbook(self, entry_id: int, payload: dict[str, Any]) -> dict | None:
        fields = [f for f in ("title","category","description","rules","checklist","notes","sections","review_fields") if f in payload]
        if not fields:
            return None
        with self.database.connect() as connection:
            connection.execute(
                f"UPDATE playbook_entries SET {','.join(f'{f}=?' for f in fields)},updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (*[json.dumps(payload[f]) if f in {"sections", "review_fields"} else payload.get(f) or "" for f in fields], entry_id),
            )
            row = connection.execute("SELECT * FROM playbook_entries WHERE id=?", (entry_id,)).fetchone()
        return _playbook(row) if row else None

    def delete_playbook(self, entry_id: int) -> bool:
        with self.database.connect() as connection:
            connection.execute("DELETE FROM media_attachments WHERE owner_type='playbook' AND owner_id=?", (entry_id,))
            cursor = connection.execute("DELETE FROM playbook_entries WHERE id=?", (entry_id,))
        return cursor.rowcount > 0

    def add_attachment(self, payload: dict[str, Any]) -> dict:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO media_attachments(owner_type,owner_id,slot,original_name,stored_name,mime_type,caption) VALUES (?,?,?,?,?,?,?)",
                (payload["owner_type"], payload["owner_id"], payload.get("slot") or "", payload["original_name"], payload["stored_name"], payload["mime_type"], payload.get("caption") or ""),
            )
            row = connection.execute("SELECT * FROM media_attachments WHERE id=?", (cursor.lastrowid,)).fetchone()
        return dict(row)

    def attachments(self, owner_type: str, owner_id: int) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM media_attachments WHERE owner_type=? AND owner_id=? ORDER BY slot,created_at",
                (owner_type, owner_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_attachment(self, attachment_id: int) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM media_attachments WHERE id=?", (attachment_id,)).fetchone()
            if row:
                connection.execute("DELETE FROM media_attachments WHERE id=?", (attachment_id,))
        return dict(row) if row else None


_NON_NULL_TEXT = {
    "source", "name", "account", "ticker", "direction", "status", "trade_type", "setup",
    "market_condition", "entry_timeframe", "timeframe_alignment", "dxy", "session_time",
    "tf_type", "wick", "analysis", "entry_notes", "management", "learning", "notes", "override_reason", "position_currency",
    "external_provider", "external_id", "external_order_id", "setup_grade", "plan_followed", "external_account_key",
}

def _encode(value: Any, column: str) -> Any:
    if column in {"timeframe_notes", "source_metadata", "review_data"}:
        return json.dumps(value or {}) if not isinstance(value, str) else value
    if value is None and column in _NON_NULL_TEXT:
        return ""
    return value


def _trade(row) -> dict:
    result = dict(row)
    try:
        result["timeframe_notes"] = json.loads(result.get("timeframe_notes") or "{}")
    except json.JSONDecodeError:
        result["timeframe_notes"] = {}
    try:
        result["source_metadata"] = json.loads(result.get("source_metadata") or "{}")
    except json.JSONDecodeError:
        result["source_metadata"] = {}
    try:
        result["review_data"] = json.loads(result.get("review_data") or "{}")
    except (ValueError, TypeError):
        result["review_data"] = {}
    return result


def _playbook(row):
    result = dict(row)
    for field, default in (("sections", {}), ("review_fields", [])):
        try:
            result[field] = json.loads(result.get(field) or json.dumps(default))
        except (ValueError, TypeError):
            result[field] = default
    return result
