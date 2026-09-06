from app.backtesting.strategies.base import Strategy, StrategySpec
from app.backtesting.strategies.registry import StrategyRegistry


class DummyStrategy(Strategy):
    spec = StrategySpec(
        key="dummy",
        name="Dummy",
        defaults={"risk_reward": 1.0},
        timeframes=("5m", "1h"),
    )


def test_strategy_plugins_are_parameterised():
    registry = StrategyRegistry()
    registry.register(DummyStrategy)

    strategy = registry.create("dummy", risk_reward=0.75)

    assert strategy.params["risk_reward"] == 0.75
    assert strategy.spec.timeframes == ("5m", "1h")
