from app.backtesting.strategies.base import Strategy


class StrategyRegistry:
    def __init__(self):
        self._items: dict[str, type[Strategy]] = {}

    def register(self, strategy: type[Strategy]) -> type[Strategy]:
        key = strategy.spec.key
        if key in self._items:
            raise ValueError(f"Strategy '{key}' is already registered")
        self._items[key] = strategy
        return strategy

    def create(self, key: str, **params) -> Strategy:
        try:
            return self._items[key](**params)
        except KeyError as exc:
            raise KeyError(f"Unknown strategy '{key}'") from exc

    def specs(self):
        return [item.spec for item in self._items.values()]


strategy_registry = StrategyRegistry()
