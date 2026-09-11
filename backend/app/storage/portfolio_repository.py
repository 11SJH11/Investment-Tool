from __future__ import annotations

from app.storage.database import Database


PORTFOLIO_COLUMNS = (
    "account", "ticker", "action", "occurred_at", "quantity", "price", "fees", "note",
    "input_mode", "input_amount", "base_currency", "asset_currency", "fx_rate", "fx_source",
    "price_source", "price_timestamp", "price_overridden", "fees_currency",
)


class PortfolioRepository:
    def __init__(self, database: Database):
        self.database = database

    def list_transactions(self, account: str | None = None) -> list[dict]:
        with self.database.connect() as connection:
            if account:
                rows = connection.execute(
                    "SELECT * FROM portfolio_transactions WHERE account=? ORDER BY occurred_at, id",
                    (account,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM portfolio_transactions ORDER BY occurred_at, id"
                ).fetchall()
        return [dict(row) for row in rows]

    def add_transaction(self, payload: dict) -> dict:
        values = []
        for column in PORTFOLIO_COLUMNS:
            value = payload.get(column)
            if column == "account": value = value or "Main"
            elif column == "ticker": value = str(value or "").upper()
            elif column == "action": value = str(value or "").upper()
            elif column == "fees": value = float(value or 0)
            elif column == "note": value = value or ""
            elif column == "input_mode": value = value or "quantity"
            elif column == "base_currency": value = value or "GBP"
            elif column == "asset_currency": value = value or "USD"
            elif column == "price_overridden": value = 1 if value else 0
            values.append(value)
        with self.database.connect() as connection:
            cursor = connection.execute(
                f"INSERT INTO portfolio_transactions({','.join(PORTFOLIO_COLUMNS)}) VALUES ({','.join('?' for _ in PORTFOLIO_COLUMNS)})",
                values,
            )
            row = connection.execute(
                "SELECT * FROM portfolio_transactions WHERE id=?", (cursor.lastrowid,)
            ).fetchone()
        return dict(row)

    def get_transaction(self, transaction_id: int) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM portfolio_transactions WHERE id=?", (transaction_id,)).fetchone()
        return dict(row) if row else None

    def delete_transaction(self, transaction_id: int) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM portfolio_transactions WHERE id=?", (transaction_id,)
            )
        return cursor.rowcount > 0

    def accounts(self) -> list[str]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT DISTINCT account FROM portfolio_transactions ORDER BY account"
            ).fetchall()
        return [row["account"] for row in rows]
