from __future__ import annotations

import json
from typing import Any

from app.storage.database import Database


_ALLOWED_ROLES = {"development", "validation", "out_of_sample", "unclassified"}


class BacktestRunRepository:
    """Persist immutable backtest snapshots plus small editable run metadata.

    Results are intentionally stored as a snapshot rather than re-computed when a
    run is opened. That makes comparisons honest even after strategy code, cached
    data, or execution defaults change. Users can explicitly duplicate settings
    into a new run when they want to re-test under the latest code/data.
    """

    def __init__(self, database: Database):
        self.database = database

    def create(
        self, *, config: dict[str, Any], result: dict[str, Any], name: str = "", notes: str = "",
        test_role: str = "development", experiment_group: str = "", tags: list[str] | None = None,
    ) -> dict[str, Any]:
        role = _normalise_role(test_role)
        strategy = result.get("strategy") or {}
        metrics = result.get("metrics") or {}
        symbols = result.get("symbols") or config.get("symbols") or []
        strategy_key = str(strategy.get("key") or config.get("strategy_key") or "")
        strategy_name = str(strategy.get("name") or strategy_key or "Unknown strategy")
        start_date = str(config.get("start_date") or str(result.get("start") or "")[:10])
        end_date = str(config.get("end_date") or str(result.get("end") or "")[:10])
        primary_timeframe = str(result.get("primary_timeframe") or config.get("primary_timeframe") or "")
        session = str(result.get("session") or config.get("session") or "regular")
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO backtest_runs(
                    name, notes, test_role, experiment_group, tags, strategy_key, strategy_name, symbols,
                    start_date, end_date, primary_timeframe, session,
                    config_json, result_json, trades, expectancy_r, total_r,
                    net_pnl, return_pct, max_drawdown_pct
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(name or ""), str(notes or ""), role, str(experiment_group or ""),
                    json.dumps(_normalise_tags(tags), separators=(",", ":")), strategy_key, strategy_name,
                    json.dumps(symbols, separators=(",", ":")), start_date, end_date,
                    primary_timeframe, session,
                    json.dumps(config, separators=(",", ":"), default=str),
                    json.dumps(result, separators=(",", ":"), default=str),
                    int(metrics.get("trades") or 0), _float_or_none(metrics.get("expectancy_r")),
                    _float_or_none(metrics.get("total_r")), _float_or_none(metrics.get("net_pnl")),
                    _float_or_none(metrics.get("return_pct")), _float_or_none(metrics.get("max_drawdown_pct")),
                ),
            )
            run_id = int(cursor.lastrowid)
        return self.get(run_id)

    def list(self, *, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = min(max(int(limit), 1), 500)
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, notes, test_role, experiment_group, tags, strategy_key, strategy_name, symbols,
                       start_date, end_date, primary_timeframe, session, trades,
                       expectancy_r, total_r, net_pnl, return_pct, max_drawdown_pct,
                       created_at, updated_at
                       , json_extract(result_json, '$.metrics.win_rate_pct') AS win_rate_pct
                       , json_extract(result_json, '$.metrics.profit_factor_r') AS profit_factor_r
                FROM backtest_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [_summary(dict(row)) for row in rows]

    def get(self, run_id: int) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM backtest_runs WHERE id = ?", (int(run_id),)).fetchone()
        if row is None:
            raise ValueError(f"Backtest run {run_id} was not found")
        item = dict(row)
        item["symbols"] = _loads(item.get("symbols"), [])
        item["tags"] = _loads(item.get("tags"), [])
        item["config"] = _loads(item.pop("config_json", None), {})
        item["result"] = _loads(item.pop("result_json", None), {})
        return item

    def list_by_experiment(self, experiment_group: str) -> list[dict[str, Any]]:
        group = str(experiment_group or "").strip()
        if not group:
            return []
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT id FROM backtest_runs WHERE experiment_group = ? ORDER BY id", (group,)
            ).fetchall()
        return [self.get(int(row["id"])) for row in rows]


    def update_metadata(
        self, run_id: int, *, name: str | None = None, notes: str | None = None,
        test_role: str | None = None, tags: list[str] | None = None,
    ) -> dict[str, Any]:
        existing = self.get(run_id)
        role = existing["test_role"] if test_role is None else _normalise_role(test_role)
        new_name = existing["name"] if name is None else str(name)
        new_notes = existing["notes"] if notes is None else str(notes)
        new_tags = existing.get("tags", []) if tags is None else _normalise_tags(tags)
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE backtest_runs
                SET name = ?, notes = ?, test_role = ?, tags = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (new_name, new_notes, role, json.dumps(new_tags, separators=(",", ":")), int(run_id)),
            )
        return self.get(run_id)

    def delete(self, run_id: int) -> None:
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM backtest_runs WHERE id = ?", (int(run_id),))
            if cursor.rowcount == 0:
                raise ValueError(f"Backtest run {run_id} was not found")


def _normalise_tags(values) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = values.split(",")
    result = []
    for value in values:
        tag = str(value or "").strip()
        if tag and tag not in result:
            result.append(tag[:40])
    return result[:20]


def _normalise_role(value: str | None) -> str:
    role = str(value or "development").strip().lower()
    if role not in _ALLOWED_ROLES:
        raise ValueError("test_role must be development, validation, out_of_sample or unclassified")
    return role


def _float_or_none(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _loads(value, fallback):
    if value in (None, ""):
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _summary(item: dict[str, Any]) -> dict[str, Any]:
    item = dict(item)
    item["symbols"] = _loads(item.get("symbols"), [])
    item["tags"] = _loads(item.get("tags"), [])
    return item
