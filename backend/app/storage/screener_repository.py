from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.storage.database import Database


FUNDAMENTAL_COLUMNS = (
    "ticker", "cik", "company_name", "fiscal_year", "period_end", "revenue",
    "revenue_growth_yoy", "net_income", "net_margin", "operating_income",
    "operating_margin", "assets", "liabilities", "equity", "cash",
    "operating_cash_flow", "capital_expenditure", "free_cash_flow",
    "eps_diluted", "shares_outstanding", "return_on_equity", "source",
)


@dataclass(frozen=True)
class ScreenerFilters:
    query: str = ""
    exchange: str | None = None
    # "stock" is a convenience group: common shares + ADRs + REITs.
    security_type: str | None = "stock"
    tradable: bool | None = None
    fractionable: bool | None = None
    shortable: bool | None = None
    min_price: float | None = None
    max_price: float | None = None
    min_market_cap: float | None = None
    max_market_cap: float | None = None
    min_pe: float | None = None
    max_pe: float | None = None
    min_revenue_growth: float | None = None
    min_net_margin: float | None = None
    min_operating_margin: float | None = None
    min_roe: float | None = None
    positive_fcf: bool | None = None
    require_fundamentals: bool = False


class ScreenerRepository:
    def __init__(self, database: Database):
        self.database = database

    def upsert_fundamentals(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        rows = [tuple(record.get(column) for column in FUNDAMENTAL_COLUMNS) for record in records]
        placeholders = ",".join("?" for _ in FUNDAMENTAL_COLUMNS)
        update_columns = [c for c in FUNDAMENTAL_COLUMNS if c != "ticker"]
        update_sql = ",\n                    ".join(
            f"{column}=excluded.{column}" for column in update_columns
        )
        with self.database.connect() as connection:
            connection.executemany(
                f"""
                INSERT INTO fundamental_metrics({','.join(FUNDAMENTAL_COLUMNS)})
                VALUES ({placeholders})
                ON CONFLICT(ticker) DO UPDATE SET
                    {update_sql},
                    updated_at=CURRENT_TIMESTAMP
                """,
                rows,
            )
        return len(rows)

    def upsert_snapshot(self, ticker: str, price: float, timestamp: datetime | str, source: str) -> None:
        stamp = timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp)
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO market_snapshots(ticker, price, timestamp, source)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    price=excluded.price,
                    timestamp=excluded.timestamp,
                    source=excluded.source,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (ticker.upper(), float(price), stamp, source),
            )

    def upsert_snapshots(self, snapshots: list[dict[str, Any]], source: str) -> int:
        rows = []
        for item in snapshots:
            if item.get("price") is None or not item.get("ticker") or not item.get("timestamp"):
                continue
            rows.append((str(item["ticker"]).upper(), float(item["price"]), str(item["timestamp"]), source))
        with self.database.connect() as connection:
            connection.executemany(
                """
                INSERT INTO market_snapshots(ticker, price, timestamp, source)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    price=excluded.price,
                    timestamp=excluded.timestamp,
                    source=excluded.source,
                    updated_at=CURRENT_TIMESTAMP
                """,
                rows,
            )
        return len(rows)

    def counts(self) -> dict[str, Any]:
        with self.database.connect() as connection:
            fundamentals = connection.execute(
                "SELECT COUNT(*) AS count, MAX(updated_at) AS updated_at FROM fundamental_metrics"
            ).fetchone()
            prices = connection.execute(
                "SELECT COUNT(*) AS count, MAX(timestamp) AS data_timestamp, MAX(updated_at) AS updated_at FROM market_snapshots"
            ).fetchone()
        return {
            "fundamentals": int(fundamentals["count"]),
            "fundamentals_updated_at": fundamentals["updated_at"],
            "prices": int(prices["count"]),
            "price_data_timestamp": prices["data_timestamp"],
            "prices_updated_at": prices["updated_at"],
        }

    def get_metrics(self, ticker: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT s.ticker, s.security_type,
                       f.cik, f.company_name, f.fiscal_year, f.period_end,
                       f.revenue, f.revenue_growth_yoy, f.net_income, f.net_margin,
                       f.operating_income, f.operating_margin, f.assets, f.liabilities,
                       f.equity, f.cash, f.operating_cash_flow, f.capital_expenditure,
                       f.free_cash_flow, f.eps_diluted, f.shares_outstanding,
                       f.return_on_equity, f.source AS fundamental_source,
                       f.updated_at AS fundamentals_updated_at,
                       m.price, m.timestamp AS price_timestamp,
                       m.source AS price_source, m.updated_at AS price_updated_at,
                       CASE WHEN f.ticker IS NOT NULL THEN 1 ELSE 0 END AS has_fundamentals,
                       CASE WHEN f.shares_outstanding IS NOT NULL AND m.price IS NOT NULL
                            THEN f.shares_outstanding * m.price END AS market_cap,
                       CASE WHEN f.eps_diluted IS NOT NULL AND f.eps_diluted != 0 AND m.price IS NOT NULL
                            THEN m.price / f.eps_diluted END AS pe_ratio
                FROM securities s
                LEFT JOIN fundamental_metrics f ON f.ticker=s.ticker
                LEFT JOIN market_snapshots m ON m.ticker=s.ticker
                WHERE s.ticker=?
                """,
                (ticker.upper(),),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["has_fundamentals"] = bool(item.get("has_fundamentals"))
        return item

    def screen(
        self,
        filters: ScreenerFilters,
        *,
        sort_by: str = "ticker",
        sort_dir: str = "asc",
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, list[dict]]:
        allowed_sort = {
            "ticker": "s.ticker", "name": "s.name", "exchange": "s.exchange",
            "security_type": "s.security_type", "price": "m.price",
            "market_cap": "market_cap", "pe_ratio": "pe_ratio",
            "revenue_growth_yoy": "f.revenue_growth_yoy", "net_margin": "f.net_margin",
            "operating_margin": "f.operating_margin", "return_on_equity": "f.return_on_equity",
            "free_cash_flow": "f.free_cash_flow",
        }
        order = allowed_sort.get(sort_by, "s.ticker")
        direction = "DESC" if sort_dir.lower() == "desc" else "ASC"
        where: list[str] = []
        params: list[Any] = []

        if filters.query.strip():
            like = f"%{filters.query.strip().upper()}%"
            where.append("(UPPER(s.ticker) LIKE ? OR UPPER(s.name) LIKE ?)")
            params.extend([like, like])
        if filters.exchange:
            where.append("UPPER(s.exchange)=?")
            params.append(filters.exchange.upper())
        if filters.security_type and filters.security_type != "all":
            if filters.security_type == "stock":
                where.append("s.security_type IN ('common_stock','adr','reit')")
            else:
                where.append("s.security_type=?")
                params.append(filters.security_type)
        for field, value in (("tradable", filters.tradable), ("fractionable", filters.fractionable), ("shortable", filters.shortable)):
            if value is not None:
                where.append(f"s.{field}=?")
                params.append(int(value))
        if filters.require_fundamentals:
            where.append("f.ticker IS NOT NULL")

        numeric_filters = (
            ("m.price >= ?", filters.min_price), ("m.price <= ?", filters.max_price),
            ("(f.shares_outstanding * m.price) >= ?", filters.min_market_cap),
            ("(f.shares_outstanding * m.price) <= ?", filters.max_market_cap),
            ("(m.price / NULLIF(f.eps_diluted, 0)) >= ?", filters.min_pe),
            ("(m.price / NULLIF(f.eps_diluted, 0)) <= ?", filters.max_pe),
            ("f.revenue_growth_yoy >= ?", filters.min_revenue_growth),
            ("f.net_margin >= ?", filters.min_net_margin),
            ("f.operating_margin >= ?", filters.min_operating_margin),
            ("f.return_on_equity >= ?", filters.min_roe),
        )
        for clause, value in numeric_filters:
            if value is not None:
                where.append(clause)
                params.append(value)
        if filters.positive_fcf is True:
            where.append("f.free_cash_flow > 0")
        elif filters.positive_fcf is False:
            where.append("f.free_cash_flow <= 0")

        where_sql = "WHERE " + " AND ".join(where) if where else ""
        select_sql = f"""
            FROM securities s
            LEFT JOIN fundamental_metrics f ON f.ticker=s.ticker
            LEFT JOIN market_snapshots m ON m.ticker=s.ticker
            {where_sql}
        """
        with self.database.connect() as connection:
            total = int(connection.execute(f"SELECT COUNT(*) {select_sql}", params).fetchone()[0])
            rows = connection.execute(
                f"""
                SELECT s.ticker, s.name, s.exchange, s.asset_type, s.security_type, s.tradable,
                       s.fractionable, s.shortable, s.cik,
                       m.price, m.timestamp AS price_timestamp, m.source AS price_source,
                       m.updated_at AS price_updated_at,
                       f.period_end, f.revenue, f.revenue_growth_yoy,
                       f.net_margin, f.operating_margin, f.free_cash_flow,
                       f.eps_diluted, f.shares_outstanding, f.return_on_equity,
                       f.updated_at AS fundamentals_updated_at,
                       CASE WHEN f.shares_outstanding IS NOT NULL AND m.price IS NOT NULL
                            THEN f.shares_outstanding * m.price END AS market_cap,
                       CASE WHEN f.eps_diluted IS NOT NULL AND f.eps_diluted != 0 AND m.price IS NOT NULL
                            THEN m.price / f.eps_diluted END AS pe_ratio
                {select_sql}
                ORDER BY {order} {direction} NULLS LAST, s.ticker ASC
                LIMIT ? OFFSET ?
                """,
                [*params, max(1, min(limit, 500)), max(0, offset)],
            ).fetchall()
        return total, [_normalize_row(row) for row in rows]


def _normalize_row(row) -> dict:
    item = dict(row)
    for field in ("tradable", "fractionable", "shortable"):
        if item.get(field) is not None:
            item[field] = bool(item[field])
    return item
