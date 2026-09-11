from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class IndicatorSpec:
    key: str
    name: str
    overlay: bool = True
    defaults: dict[str, int | float | str | bool] = field(default_factory=dict)
    causal: bool = False


class Indicator(ABC):
    spec: IndicatorSpec

    @abstractmethod
    def calculate(self, bars: pd.DataFrame, **params) -> pd.DataFrame | pd.Series: ...
