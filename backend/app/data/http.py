from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx


class ProviderHttpError(RuntimeError):
    pass


_SENSITIVE_QUERY_KEYS = {
    "apikey",
    "api_key",
    "key",
    "token",
    "access_token",
    "authorization",
}


class JsonHttpClient:
    """Small pooled/retrying HTTP client shared by external data providers.

    Provider credentials are deliberately scrubbed from raised exceptions. This
    matters because httpx's default HTTPStatusError string includes the complete
    request URL, which can otherwise expose query-string API keys in terminals,
    issue reports, screenshots, or copied tracebacks.
    """

    def __init__(self, timeout_seconds: float = 30.0, max_attempts: int = 3):
        self.max_attempts = max_attempts
        self._client = httpx.Client(timeout=timeout_seconds, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def get_json(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
        return self._get(url, params=params, headers=headers).json()

    def get_bytes(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout_seconds: float | None = None) -> bytes:
        return self._get(url, params=params, headers=headers, timeout_seconds=timeout_seconds).content

    def download_file(
        self,
        url: str,
        destination: Path,
        *,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 300.0,
    ) -> Path:
        """Stream a large provider file to disk instead of holding it in RAM."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".part")
        last_error: str | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                with self._client.stream("GET", url, headers=headers, timeout=timeout_seconds) as response:
                    response.raise_for_status()
                    with temporary.open("wb") as handle:
                        for chunk in response.iter_bytes():
                            handle.write(chunk)
                temporary.replace(destination)
                return destination
            except httpx.HTTPStatusError as exc:
                last_error = _safe_http_status_error(exc)
                temporary.unlink(missing_ok=True)
                if _is_retryable_status(exc.response.status_code) and attempt < self.max_attempts:
                    time.sleep(_retry_delay(exc.response, attempt))
                    continue
                break
            except httpx.HTTPError as exc:
                last_error = type(exc).__name__
                temporary.unlink(missing_ok=True)
                if attempt < self.max_attempts:
                    time.sleep(0.5 * attempt)
                    continue
                break
        raise ProviderHttpError(f"GET {_redact_url(url)} failed: {last_error}")

    def _get(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout_seconds: float | None = None) -> httpx.Response:
        last_error: str | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                kwargs = {"params": params, "headers": headers}
                if timeout_seconds is not None:
                    kwargs["timeout"] = timeout_seconds
                response = self._client.get(url, **kwargs)
                if _is_retryable_status(response.status_code) and attempt < self.max_attempts:
                    time.sleep(_retry_delay(response, attempt))
                    continue
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                last_error = _safe_http_status_error(exc)
                # Ordinary 4xx errors are deterministic request/auth failures; do
                # not hammer a rate-limited provider with identical retries.
                if _is_retryable_status(exc.response.status_code) and attempt < self.max_attempts:
                    time.sleep(_retry_delay(exc.response, attempt))
                    continue
                break
            except httpx.HTTPError as exc:
                last_error = type(exc).__name__
                if attempt < self.max_attempts:
                    time.sleep(0.25 * attempt)
                    continue
                break
        raise ProviderHttpError(f"GET {_redact_url(url)} failed: {last_error}")


def _is_retryable_status(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(float(retry_after), 0.0)
        except ValueError:
            pass
    return 0.25 * attempt


def _safe_http_status_error(exc: httpx.HTTPStatusError) -> str:
    response = exc.response
    safe_url = _redact_url(str(response.request.url))
    detail = _response_detail(response)
    suffix = f": {detail}" if detail else ""
    return f"HTTP {response.status_code} {response.reason_phrase} for {safe_url}{suffix}"


def _response_detail(response: httpx.Response, max_chars: int = 700) -> str:
    """Return a concise provider error body without echoing credentials."""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            # Common provider schemas use error/message/detail. Avoid dumping the
            # full payload because providers can occasionally echo request data.
            bits = []
            for key in ("error", "message", "detail", "status", "request_id"):
                value = payload.get(key)
                if value not in (None, ""):
                    bits.append(f"{key}={value}")
            text = "; ".join(bits) if bits else json.dumps(payload, ensure_ascii=False)
        else:
            text = json.dumps(payload, ensure_ascii=False)
    except Exception:
        text = response.text.strip()
    text = _redact_text(text)
    if len(text) > max_chars:
        text = text[:max_chars] + "…"
    return text


def _redact_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        safe_pairs = [
            (key, "<redacted>" if key.lower() in _SENSITIVE_QUERY_KEYS else val)
            for key, val in pairs
        ]
        path = re.sub(r"(/accounts/)[^/]+", r"\1<redacted>", parts.path)
        return urlunsplit((parts.scheme, parts.netloc, path, urlencode(safe_pairs), parts.fragment))
    except Exception:
        return _redact_text(value)


def _redact_text(value: str) -> str:
    # Best-effort fallback for provider-supplied error strings containing obvious
    # key=value credentials. Query URLs are handled more rigorously by _redact_url.
    text = str(value or "")
    text = re.sub(r"(?i)Bearer\s+[^\s\"',;]+", "Bearer <redacted>", text)
    text = re.sub(r'(?i)([\"\x27]?(?:access_token|api_key|apikey|token|authorization)[\"\x27]?\s*:\s*)[\"\x27]?[^\s\"\x27,;}]+', r'\1<redacted>', text)
    for key in _SENSITIVE_QUERY_KEYS:
        marker = f"{key}="
        lower = text.lower()
        start = lower.find(marker)
        while start != -1:
            value_start = start + len(marker)
            value_end = value_start
            while value_end < len(text) and text[value_end] not in "& ;,\n\r\t\"'":
                value_end += 1
            text = text[:value_start] + "<redacted>" + text[value_end:]
            lower = text.lower()
            start = lower.find(marker, value_start + len("<redacted>"))
    return text
