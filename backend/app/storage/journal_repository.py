from __future__ import annotations

import json
from datetime import date
from typing import Any

from app.storage.database import Database


TRADE_COLUMNS = (
    "source", "name", "account", "ticker", "direction", "status", "opened_at", "closed_at",
    "entry_price", "exit_price", "quantity", "position_amount", "position_currency", "stop_loss", "take_profit", "fees", "result",
    "result_source", "pnl_amount", "pnl_pct", "r_multiple", "planned_rr", "pnl_override", "override_reason", "pnl_source", "trade_type", "setup", "market_condition",
    "entry_timeframe", "timeframe_alignment", "dxy", "session_time", "tf_type", "wick", "analysis",
    "entry_notes", "management", "learning", "notes", "timeframe_notes",
    "external_provider", "external_id", "external_order_id", "source_metadata", "imported_at",
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


    def report(self, filters: dict | None = None) -> dict:
        filters = filters or {}
        trades = self.list_trades(limit=5000)
        def keep(t):
            if filters.get("source") and t.get("source") != filters["source"]: return False
            if filters.get("ticker") and filters["ticker"].upper() not in str(t.get("ticker") or "").upper(): return False
            if filters.get("direction") and t.get("direction") != filters["direction"]: return False
            if filters.get("result") and t.get("result") != filters["result"]: return False
            if filters.get("setup") and filters["setup"].lower() not in str(t.get("setup") or "").lower(): return False
            if filters.get("entry_timeframe") and t.get("entry_timeframe") != filters["entry_timeframe"]: return False
            if filters.get("market_condition") and filters["market_condition"].lower() not in str(t.get("market_condition") or "").lower(): return False
            opened = str(t.get("opened_at") or "")
            if filters.get("date_from") and opened[:10] < filters["date_from"]: return False
            if filters.get("date_to") and opened[:10] > filters["date_to"]: return False
            return True
        rows=[t for t in trades if keep(t)]
        from datetime import datetime
        from zoneinfo import ZoneInfo
        def dt(t):
            try:
                value=datetime.fromisoformat(str(t.get("opened_at") or "").replace("Z","+00:00"))
                if value.tzinfo is None: value=value.replace(tzinfo=ZoneInfo("UTC"))
                return value.astimezone(ZoneInfo("America/New_York"))
            except Exception: return None
        def group(name, fn):
            buckets={}
            for t in rows:
                key=fn(t) or "Unknown"; buckets.setdefault(str(key),[]).append(t)
            out=[]
            for key,items in buckets.items():
                rs=[float(x["r_multiple"]) for x in items if x.get("r_multiple") is not None]
                wins=sum(1 for x in items if x.get("result")=="win"); losses=sum(1 for x in items if x.get("result")=="loss")
                pnl=sum(float(x.get("pnl_amount") or 0) for x in items)
                pos=sum(x for x in rs if x>0); neg=abs(sum(x for x in rs if x<0))
                out.append({name:key,"trades":len(items),"win_rate":wins/(wins+losses)*100 if wins+losses else None,"average_r":sum(rs)/len(rs) if rs else None,"total_r":sum(rs) if rs else None,"profit_factor_r":pos/neg if neg else (None if not pos else 999.0),"pnl":pnl})
            return sorted(out,key=lambda x:(x["trades"],x.get("total_r") or 0),reverse=True)
        rs=[float(x["r_multiple"]) for x in rows if x.get("r_multiple") is not None]
        wins=sum(1 for x in rows if x.get("result")=="win"); losses=sum(1 for x in rows if x.get("result")=="loss")
        durations=[]
        for t in rows:
            try:
                a=datetime.fromisoformat(str(t.get("opened_at") or "").replace("Z","+00:00")); b=datetime.fromisoformat(str(t.get("closed_at") or "").replace("Z","+00:00")); durations.append((b-a).total_seconds()/60)
            except Exception: pass
        return {
          "filters":filters,"trades":rows,
          "summary":{"trades":len(rows),"win_rate":wins/(wins+losses)*100 if wins+losses else None,"average_r":sum(rs)/len(rs) if rs else None,"total_r":sum(rs) if rs else None,"average_duration_min":sum(durations)/len(durations) if durations else None},
          "breakdowns":{
            "symbol":group("symbol",lambda t:t.get("ticker")),
            "setup":group("setup",lambda t:t.get("setup") or "Unlabelled"),
            "direction":group("direction",lambda t:t.get("direction")),
            "timeframe":group("timeframe",lambda t:t.get("entry_timeframe") or "Unlabelled"),
            "market_condition":group("market_condition",lambda t:t.get("market_condition") or "Unlabelled"),
            "weekday":group("weekday",lambda t:dt(t).strftime("%A") if dt(t) else "Unknown"),
            "entry_hour":group("entry_hour",lambda t:dt(t).strftime("%H:00") if dt(t) else "Unknown"),
            "source":group("source",lambda t:t.get("source")),
          }
        }

    def calendar(self, month: str | None = None, source: str | None = None) -> list[dict]:
        where = ["COALESCE(substr(closed_at,1,10), substr(opened_at,1,10)) IS NOT NULL"]
        params: list[Any] = []
        if month:
            where.append("substr(COALESCE(closed_at,opened_at),1,7)=?")
            params.append(month)
        if source:
            where.append("source=?")
            params.append(source)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT substr(COALESCE(closed_at,opened_at),1,10) AS day,
                       COUNT(*) AS trades,
                       SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) AS wins,
                       SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) AS losses,
                       SUM(CASE WHEN result='breakeven' THEN 1 ELSE 0 END) AS breakevens,
                       SUM(COALESCE(pnl_amount,0)) AS pnl_amount,
                       SUM(COALESCE(r_multiple,0)) AS r_total
                FROM journal_trades
                WHERE {' AND '.join(where)}
                GROUP BY day ORDER BY day
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def analytics(self, source: str | None = None) -> dict:
        where = "WHERE source=?" if source else ""
        params = (source,) if source else ()
        with self.database.connect() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*) AS trades,
                       SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) AS wins,
                       SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) AS losses,
                       SUM(CASE WHEN result='breakeven' THEN 1 ELSE 0 END) AS breakevens,
                       AVG(r_multiple) AS avg_r,
                       AVG(planned_rr) AS avg_planned_rr,
                       SUM(COALESCE(r_multiple,0)) AS total_r,
                       SUM(COALESCE(pnl_amount,0)) AS total_pnl,
                       AVG(pnl_pct) AS avg_pnl_pct
                FROM journal_trades {where}
                """,
                params,
            ).fetchone()
            by_source = connection.execute(
                "SELECT source, COUNT(*) AS trades, SUM(COALESCE(pnl_amount,0)) AS total_pnl FROM journal_trades GROUP BY source ORDER BY trades DESC"
            ).fetchall()
            by_setup = connection.execute(
                f"SELECT setup, COUNT(*) AS trades, SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) AS wins, AVG(r_multiple) AS avg_r FROM journal_trades {where + (' AND ' if where else 'WHERE ')} setup!='' GROUP BY setup ORDER BY trades DESC LIMIT 20",
                params,
            ).fetchall()
            pnl_by_currency = connection.execute(
                f"SELECT COALESCE(NULLIF(position_currency,''),'USD') AS currency, SUM(COALESCE(pnl_amount,0)) AS total_pnl FROM journal_trades {where} GROUP BY COALESCE(NULLIF(position_currency,''),'USD') ORDER BY currency",
                params,
            ).fetchall()
        result = dict(row)
        decided = int(result.get("wins") or 0) + int(result.get("losses") or 0)
        result["win_rate"] = (int(result.get("wins") or 0) / decided * 100) if decided else None
        result["by_source"] = [dict(item) for item in by_source]
        result["by_setup"] = [{**dict(item), "win_rate": (item["wins"] / item["trades"] * 100) if item["trades"] else None} for item in by_setup]
        result["pnl_by_currency"] = [dict(item) for item in pnl_by_currency]

        with self.database.connect() as connection:
            curve_rows = connection.execute(
                f"SELECT result, r_multiple, pnl_amount FROM journal_trades {where} ORDER BY COALESCE(closed_at,opened_at,created_at), id",
                params,
            ).fetchall()
        equity_r = 0.0
        peak_r = 0.0
        max_drawdown_r = 0.0
        losing_streak = 0
        longest_losing_streak = 0
        gross_win_r = 0.0
        gross_loss_r = 0.0
        for item in curve_rows:
            r = float(item["r_multiple"] or 0)
            equity_r += r
            peak_r = max(peak_r, equity_r)
            max_drawdown_r = min(max_drawdown_r, equity_r - peak_r)
            if r > 0:
                gross_win_r += r
            elif r < 0:
                gross_loss_r += abs(r)
            if item["result"] == "loss":
                losing_streak += 1
                longest_losing_streak = max(longest_losing_streak, losing_streak)
            elif item["result"] in {"win", "breakeven"}:
                losing_streak = 0
        result["max_drawdown_r"] = max_drawdown_r
        result["longest_losing_streak"] = longest_losing_streak
        result["profit_factor_r"] = (gross_win_r / gross_loss_r) if gross_loss_r > 0 else (None if gross_win_r == 0 else "inf")
        return result

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
                "INSERT INTO playbook_entries(title,category,description,rules,checklist,notes) VALUES (?,?,?,?,?,?)",
                (payload["title"], payload.get("category") or "Entry Model", payload.get("description") or "", payload.get("rules") or "", payload.get("checklist") or "", payload.get("notes") or ""),
            )
            row = connection.execute("SELECT * FROM playbook_entries WHERE id=?", (cursor.lastrowid,)).fetchone()
        return dict(row)

    def list_playbook(self) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM playbook_entries ORDER BY category,title").fetchall()
        return [dict(row) for row in rows]

    def update_playbook(self, entry_id: int, payload: dict[str, Any]) -> dict | None:
        fields = [f for f in ("title","category","description","rules","checklist","notes") if f in payload]
        if not fields:
            return None
        with self.database.connect() as connection:
            connection.execute(
                f"UPDATE playbook_entries SET {','.join(f'{f}=?' for f in fields)},updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (*[payload.get(f) or "" for f in fields], entry_id),
            )
            row = connection.execute("SELECT * FROM playbook_entries WHERE id=?", (entry_id,)).fetchone()
        return dict(row) if row else None

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
    "external_provider", "external_id", "external_order_id",
}

def _encode(value: Any, column: str) -> Any:
    if column in {"timeframe_notes", "source_metadata"}:
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
    return result
