from fastapi.testclient import TestClient

from app.main import app


def test_data_status_boots_without_external_keys():
    with TestClient(app) as client:
        response = client.get("/api/data/status")

    assert response.status_code == 200
    body = response.json()
    assert "providers" in body
    assert "symbols_cached" in body
    assert set(body["providers"]) == {"alpaca", "massive", "oanda", "sec", "fred", "autochartist"}
