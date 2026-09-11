from app.data.providers.fred import FredProvider
from tests.fakes import FakeJsonHttpClient


def test_fred_snapshot_returns_latest_value_and_trend():
    def handler(url, params, headers):
        assert url.endswith("/fred/series/observations")
        assert params["file_type"] == "json"
        if params["series_id"] == "CPIAUCSL":
            assert params["units"] == "pc1"
        return {
            "observations": [
                {"date": "2026-07-01", "value": "4.25"},
                {"date": "2026-06-01", "value": "4.50"},
            ]
        }

    provider = FredProvider("fred-key", http=FakeJsonHttpClient(handler))
    result = provider.get_snapshot()

    assert result["fed_funds_rate"]["value"] == 4.25
    assert result["fed_funds_rate"]["trend"] == "falling"
    assert result["cpi_yoy"]["unit"] == "%"
