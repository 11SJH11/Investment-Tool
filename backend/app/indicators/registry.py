from app.indicators.base import Indicator


class IndicatorRegistry:
    def __init__(self):
        self._items: dict[str, type[Indicator]] = {}

    def register(self, indicator: type[Indicator]) -> type[Indicator]:
        key = indicator.spec.key
        if key in self._items:
            raise ValueError(f"Indicator '{key}' is already registered")
        self._items[key] = indicator
        return indicator

    def create(self, key: str) -> Indicator:
        try:
            return self._items[key]()
        except KeyError as exc:
            raise KeyError(f"Unknown indicator '{key}'") from exc

    def specs(self):
        return [item.spec for item in self._items.values()]


indicator_registry = IndicatorRegistry()
