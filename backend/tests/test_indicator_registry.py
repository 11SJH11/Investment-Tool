import pandas as pd

from app.indicators.base import Indicator, IndicatorSpec
from app.indicators.registry import IndicatorRegistry


class DummyIndicator(Indicator):
    spec = IndicatorSpec(key="dummy", name="Dummy", defaults={"period": 5})

    def calculate(self, bars: pd.DataFrame, **params):
        return bars["close"]


def test_indicator_plugins_can_be_registered_and_created():
    registry = IndicatorRegistry()
    registry.register(DummyIndicator)

    indicator = registry.create("dummy")

    assert indicator.spec.name == "Dummy"
    assert registry.specs()[0].defaults["period"] == 5
