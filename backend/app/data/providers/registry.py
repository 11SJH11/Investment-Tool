from typing import Any


class ProviderRegistry:
    """Keeps feature code independent from whichever external API we use."""

    def __init__(self):
        self._providers: dict[str, Any] = {}

    def register(self, kind: str, provider: Any) -> None:
        self._providers[kind] = provider

    def get(self, kind: str) -> Any:
        try:
            return self._providers[kind]
        except KeyError as exc:
            raise RuntimeError(f"No provider configured for '{kind}'") from exc

    def configured(self) -> list[str]:
        return sorted(self._providers)
