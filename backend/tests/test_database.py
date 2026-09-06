from app.storage.database import Database


def test_database_initializes_and_round_trips_setting(tmp_path):
    database = Database(tmp_path / "ledger.db")
    database.initialize()

    database.set_setting("theme", "dark")

    assert database.get_setting("theme") == "dark"
    assert database.get_setting("missing") is None
