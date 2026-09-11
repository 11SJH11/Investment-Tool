from datetime import datetime, timezone

from app.data.providers.alpaca import AlpacaProvider
from tests.fakes import FakeJsonHttpClient


def test_alpaca_lists_active_us_assets():
    def handler(url, params, headers):
        assert url.endswith("/v2/assets")
        assert params == {"status": "active", "asset_class": "us_equity"}
        assert headers["APCA-API-KEY-ID"] == "key"
        return [
            {
                "id": "asset-1",
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "exchange": "NASDAQ",
                "status": "active",
                "tradable": True,
                "fractionable": True,
                "shortable": True,
            }
        ]

    provider = AlpacaProvider("key", "secret", http=FakeJsonHttpClient(handler))
    symbols = provider.list_symbols()

    assert len(symbols) == 1
    assert symbols[0].ticker == "AAPL"
    assert symbols[0].exchange == "NASDAQ"
    assert symbols[0].fractionable is True


def test_alpaca_bars_use_sip_historical_feed_and_paginate():
    def handler(url, params, headers):
        assert url.endswith("/v2/stocks/AAPL/bars")
        assert params["timeframe"] == "5Min"
        assert params["feed"] == "sip"
        assert params["adjustment"] == "split"
        if "page_token" not in params:
            return {
                "bars": [{"t": "2026-01-02T14:30:00Z", "o": 10, "h": 11, "l": 9, "c": 10.5, "v": 100}],
                "next_page_token": "next",
            }
        assert params["page_token"] == "next"
        return {
            "bars": [{"t": "2026-01-02T14:35:00Z", "o": 10.5, "h": 12, "l": 10, "c": 11.5, "v": 200}],
            "next_page_token": None,
        }

    http = FakeJsonHttpClient(handler)
    provider = AlpacaProvider("key", "secret", historical_feed="sip", live_feed="iex", http=http)
    frame = provider.get_bars(
        "aapl",
        "5m",
        datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        datetime(2026, 1, 2, 15, 0, tzinfo=timezone.utc),
    )

    assert len(frame) == 2
    assert frame.iloc[1]["close"] == 11.5
    assert len(http.calls) == 2


def test_alpaca_latest_quote_uses_free_live_iex_feed():
    def handler(url, params, headers):
        assert url.endswith("/v2/stocks/MSFT/bars/latest")
        assert params["feed"] == "iex"
        return {"bar": {"t": "2026-01-02T14:35:00Z", "c": 420.25}}

    provider = AlpacaProvider("key", "secret", historical_feed="sip", live_feed="iex", http=FakeJsonHttpClient(handler))
    quote = provider.get_quote("msft")

    assert quote.ticker == "MSFT"
    assert quote.price == 420.25


def test_alpaca_rejects_recent_sip_history_on_basic_delay():
    from datetime import timedelta
    import pytest

    provider = AlpacaProvider(
        "key",
        "secret",
        historical_feed="sip",
        historical_delay_minutes=15,
        http=FakeJsonHttpClient(lambda *_: (_ for _ in ()).throw(AssertionError("HTTP should not be called"))),
    )
    now = datetime.now(timezone.utc)

    with pytest.raises(ValueError, match="delayed by 15 minutes"):
        provider.get_bars("AAPL", "1m", now - timedelta(hours=1), now)
