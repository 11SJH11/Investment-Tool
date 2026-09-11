from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from app.services.market_data import MarketDataService


class ExecutionPriceService:
    """Resolve an estimated historical execution price from 1-minute market bars.

    This is intentionally an estimate for portfolio bookkeeping, not a claim about the
    user's exact broker fill. A supplied price override always wins.
    """

    def __init__(self, market_data: MarketDataService | None):
        self.market_data = market_data

    def resolve(self, ticker: str, occurred_at: datetime, override: float | None = None) -> dict:
        if override is not None:
            price = float(override)
            if price <= 0:
                raise ValueError("price override must be greater than zero")
            return {"price": price, "source": "manual_override", "overridden": True, "timestamp": None}
        if self.market_data is None:
            raise ValueError("Market data is not configured. Enter the actual fill price instead.")

        at = _utc(occurred_at)
        start = at - timedelta(minutes=20)
        end = at + timedelta(minutes=20)
        bars = self.market_data.get_bars(
            ticker=ticker,
            timeframe="1m",
            start=start,
            end=end,
        )

        # Coverage can exist from an earlier empty/failed request. If the cache comes
        # back empty, make one explicit provider refresh before giving up.
        if bars.empty:
            bars = self.market_data.get_bars(
                ticker=ticker,
                timeframe="1m",
                start=start,
                end=end,
                force_refresh=True,
            )
        if bars.empty:
            raise ValueError(
                f"No 1-minute market data found near {at.isoformat()}. "
                "Use a market-hours timestamp or enter the actual fill price manually."
            )
        if "timestamp" not in bars.columns:
            raise ValueError("Historical market data is missing its timestamp column")

        work = bars.copy()
        timestamps = pd.to_datetime(work["timestamp"], utc=True, errors="coerce")
        valid = timestamps.notna() & work["close"].notna()
        work = work.loc[valid].copy()
        timestamps = timestamps.loc[valid]
        if work.empty:
            raise ValueError("Historical market data contained no usable timestamp/close rows")

        target = pd.Timestamp(at)
        distances = (timestamps - target).abs()
        closest_label = distances.idxmin()
        row = work.loc[closest_label]
        timestamp = pd.Timestamp(timestamps.loc[closest_label]).to_pydatetime().isoformat()
        return {
            "price": float(row["close"]),
            "timestamp": timestamp,
            "source": f"{self.market_data.provider.key}_1m_close_estimate",
            "overridden": False,
        }


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
