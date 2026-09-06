from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx


class ProviderHttpError(RuntimeError):
    pass


class JsonHttpClient:
    """Small pooled/retrying HTTP client shared by external data providers."""

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
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                with self._client.stream("GET", url, headers=headers, timeout=timeout_seconds) as response:
                    response.raise_for_status()
                    with temporary.open("wb") as handle:
                        for chunk in response.iter_bytes():
                            handle.write(chunk)
                temporary.replace(destination)
                return destination
            except httpx.HTTPError as exc:
                last_error = exc
                temporary.unlink(missing_ok=True)
                if attempt < self.max_attempts:
                    time.sleep(0.5 * attempt)
                    continue
                break
        raise ProviderHttpError(f"GET {url} failed: {last_error}") from last_error

    def _get(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout_seconds: float | None = None) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                kwargs = {"params": params, "headers": headers}
                if timeout_seconds is not None:
                    kwargs["timeout"] = timeout_seconds
                response = self._client.get(url, **kwargs)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < self.max_attempts:
                        retry_after = response.headers.get("Retry-After")
                        delay = float(retry_after) if retry_after and retry_after.isdigit() else 0.25 * attempt
                        time.sleep(delay)
                        continue
                response.raise_for_status()
                return response
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self.max_attempts:
                    time.sleep(0.25 * attempt)
                    continue
                break
        raise ProviderHttpError(f"GET {url} failed: {last_error}") from last_error
