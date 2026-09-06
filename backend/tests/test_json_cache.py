from app.storage.database import Database
from app.storage.json_cache import JsonCacheRepository


def test_json_cache_round_trip_and_expiry(tmp_path):
    database = Database(tmp_path / "ledger.db")
    database.initialize()
    cache = JsonCacheRepository(database)

    cache.set("demo", "key", {"value": 42}, ttl_seconds=60)
    assert cache.get("demo", "key") == {"value": 42}

    cache.set("demo", "expired", {"value": 1}, ttl_seconds=0)
    assert cache.get("demo", "expired") is None
