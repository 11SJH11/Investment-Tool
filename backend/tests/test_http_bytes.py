def test_http_client_exposes_large_file_download():
    from app.data.http import JsonHttpClient
    assert callable(getattr(JsonHttpClient, "get_bytes"))
    assert callable(getattr(JsonHttpClient, "download_file"))
