from datetime import datetime, timezone

import pandas as pd

from app.data.instruments import instrument_spec, virtual_symbols
from app.data.providers.massive_futures import MassiveFuturesProvider
from app.data.providers.oanda import OandaProvider
from app.services.chart_data import prepare_chart_bars
from tests.fakes import FakeJsonHttpClient


def test_virtual_symbols_expose_xauusd_and_nq1():
    tickers = {item["ticker"] for item in virtual_symbols()}
    assert {"XAUUSD", "NQ1!"}.issubset(tickers)
    assert instrument_spec("XAU_USD").provider_symbol == "XAU_USD"
    assert instrument_spec("NQ1!").session_profile == "futures_24h"


def test_oanda_normalises_mid_candles_without_account_id():
    def handler(url, params, headers):
        assert url.endswith("/v3/instruments/XAU_USD/candles")
        assert params["granularity"] == "M5"
        assert params["price"] == "M"
        assert headers["Authorization"] == "Bearer token"
        return {
            "candles": [
                {"complete": True, "time": "2026-08-03T12:00:00.000000000Z", "volume": 12,
                 "mid": {"o": "2400.1", "h": "2401.2", "l": "2399.9", "c": "2400.8"}},
                {"complete": False, "time": "2026-08-03T12:05:00.000000000Z", "volume": 3,
                 "mid": {"o": "2400.8", "h": "2401.0", "l": "2400.4", "c": "2400.7"}},
            ]
        }

    http = FakeJsonHttpClient(handler)
    provider = OandaProvider("token", http=http)
    frame = provider.get_bars(
        "XAUUSD", "5m",
        datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc),
        datetime(2026, 8, 3, 12, 10, tzinfo=timezone.utc),
    )
    assert len(frame) == 1
    assert frame.iloc[0]["close"] == 2400.8


def test_massive_continuous_front_stitches_dated_contracts_and_keeps_provenance():
    def handler(url, params, headers):
        assert headers["Authorization"] == "Bearer key"
        assert "apiKey" not in params
        if url.endswith("/futures/v1/contracts"):
            assert params['product_code'] == 'NQ' and params['limit'] == 1000
            assert params['type'] == 'single' and params['date']
            return {
                "results": [
                    {"ticker": "NQU6", "product_code": "NQ", "first_trade_date": "2025-06-20", "last_trade_date": "2026-09-18"},
                    {"ticker": "NQZ6", "product_code": "NQ", "first_trade_date": "2025-09-19", "last_trade_date": "2026-12-18"},
                ]
            }
        if url.endswith("/futures/v1/aggs/NQU6"):
            return {"results": [{"window_start": 1789689600000000000, "open": 25000, "high": 25010, "low": 24990, "close": 25005, "volume": 100}]}
        if url.endswith("/futures/v1/aggs/NQZ6"):
            return {"results": [{"window_start": 1789948800000000000, "open": 25050, "high": 25070, "low": 25040, "close": 25060, "volume": 120}]}
        raise AssertionError(url)

    provider = MassiveFuturesProvider("key", http=FakeJsonHttpClient(handler),roll_policy='calendar-front-v1')
    frame = provider.get_bars(
        "NQ1!", "1d",
        datetime(2026, 9, 18, tzinfo=timezone.utc),
        datetime(2026, 9, 22, tzinfo=timezone.utc),
    )
    assert frame["source_contract"].tolist() == ["NQU6", "NQZ6"]
    assert frame["close"].tolist() == [25005, 25060]


def test_24h_chart_data_is_not_filtered_to_us_equity_hours():
    frame = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-08-03T01:00:00Z", "2026-08-03T01:01:00Z", "2026-08-03T14:00:00Z"], utc=True),
        "open": [1, 2, 3], "high": [1.1, 2.1, 3.1], "low": [.9, 1.9, 2.9], "close": [1.05, 2.05, 3.05], "volume": [1, 1, 1],
    })
    prepared, aggregation = prepare_chart_bars(frame, "1m", "regular", session_profile="futures_24h")
    assert len(prepared) == 3
    assert aggregation == "provider_native_24h"


def test_oanda_latest_available_end_uses_newest_complete_candle_on_closed_market():
    def handler(url, params, headers):
        assert url.endswith('/v3/instruments/XAU_USD/candles')
        assert params['count'] == 3
        assert params['granularity'] == 'M5'
        return {
            'candles': [
                {'complete': True, 'time': '2026-09-04T20:55:00.000000000Z', 'volume': 4,
                 'mid': {'o': '4400', 'h': '4401', 'l': '4399', 'c': '4400.5'}},
                {'complete': False, 'time': '2026-09-07T21:00:00.000000000Z', 'volume': 1,
                 'mid': {'o': '4410', 'h': '4410', 'l': '4410', 'c': '4410'}},
            ]
        }

    provider = OandaProvider('token', http=FakeJsonHttpClient(handler))
    end = provider.latest_available_end(
        'XAUUSD', '5m', datetime(2026, 9, 7, 21, 5, tzinfo=timezone.utc)
    )
    assert end == datetime(2026, 9, 4, 21, 0, tzinfo=timezone.utc)


def test_oanda_latest_probe_does_not_send_future_to_timestamp():
    calls = []
    def handler(url, params, headers):
        calls.append(dict(params))
        assert "to" not in params
        return {
            "candles": [
                {"complete": True, "time": "2026-09-04T20:55:00Z", "volume": 1,
                 "mid": {"o": "4400", "h": "4401", "l": "4399", "c": "4400"}}
            ]
        }
    provider = OandaProvider("token", http=FakeJsonHttpClient(handler))
    end = provider.latest_available_end("XAUUSD", "5m", datetime(2026, 9, 7, 21, 0, tzinfo=timezone.utc))
    assert end == datetime(2026, 9, 4, 21, 0, tzinfo=timezone.utc)
    assert len(calls) == 1


def test_oanda_latest_cache_is_not_poisoned_by_historical_reference():
    def handler(url, params, headers):
        return {
            "candles": [
                {"complete": True, "time": "2026-09-04T20:55:00Z", "volume": 1,
                 "mid": {"o": "4400", "h": "4401", "l": "4399", "c": "4400"}}
            ]
        }
    provider = OandaProvider("token", http=FakeJsonHttpClient(handler))
    historical = provider.latest_available_end("XAUUSD", "5m", datetime(2026, 6, 1, tzinfo=timezone.utc))
    current = provider.latest_available_end("XAUUSD", "5m", datetime(2026, 9, 7, 21, 0, tzinfo=timezone.utc))
    assert historical == datetime(2026, 6, 1, tzinfo=timezone.utc)
    assert current == datetime(2026, 9, 4, 21, 0, tzinfo=timezone.utc)
