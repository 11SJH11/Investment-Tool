from app.data.http import _redact_text, _redact_url


def test_redact_url_hides_api_credentials():
    safe = _redact_url("https://example.test/path?apiKey=secret123&limit=5&token=abc")
    assert "secret123" not in safe
    assert "abc" not in safe
    assert "limit=5" in safe
    assert "%3Credacted%3E" in safe


def test_redact_text_hides_query_style_api_key():
    safe = _redact_text("bad request https://x.test?a=1&apiKey=secret123&limit=5")
    assert "secret123" not in safe
    assert "apiKey=<redacted>" in safe
