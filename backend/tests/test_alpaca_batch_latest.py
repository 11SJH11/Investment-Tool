from app.data.providers.alpaca import AlpacaProvider
from tests.fakes import FakeJsonHttpClient


def test_get_latest_bars_batches_symbols():
    def handler(url, params, headers):
        assert params["symbols"] == "AAPL,MSFT"
        assert params["feed"] == "iex"
        return {"bars": {
            "AAPL": {"c": 210.5, "t": "2026-08-27T15:30:00Z"},
            "MSFT": {"c": 510.0, "t": "2026-08-27T15:30:00Z"},
        }}
    provider = AlpacaProvider("key", "secret", live_feed="iex", http=FakeJsonHttpClient(handler))
    rows = provider.get_latest_bars(["aapl", "msft"])
    assert [row["ticker"] for row in rows] == ["AAPL", "MSFT"]
    assert rows[0]["price"] == 210.5
