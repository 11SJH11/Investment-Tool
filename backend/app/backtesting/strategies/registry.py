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

    def register_workspace_class(self, strategy, provenance):
        existing = self._items.get(strategy.spec.key)
        if existing is not None and existing is not strategy:
            raise ValueError('Workspace key is already registered')
        strategy.workspace_provenance = dict(provenance)
        self._items[strategy.spec.key] = strategy

    def deactivate_workspace(self, key, source_hash):
        existing = self._items.get(key)
        if existing is not None:
            if getattr(existing, 'workspace_provenance', {}).get('source_sha256') != source_hash:
                raise ValueError('Refusing to deactivate a different or built-in strategy')
            del self._items[key]


strategy_registry = StrategyRegistry()
