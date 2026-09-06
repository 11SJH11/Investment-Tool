# Ledger indicator plugin template

Indicators are shared calculations used by Strategy Lab, Research and Replay. Add a Python module under `backend/app/indicators/`; Ledger auto-discovers it.

```python
import pandas as pd
from app.indicators.base import Indicator, IndicatorSpec
from app.indicators.registry import indicator_registry


@indicator_registry.register
class MyIndicator(Indicator):
    spec = IndicatorSpec(
        key="my_indicator",
        name="My Indicator",
        overlay=False,
        defaults={"length": 14},
        causal=True,
    )

    def calculate(self, bars: pd.DataFrame, **params) -> pd.Series:
        length = int(params.get("length", self.spec.defaults["length"]))
        # Use current/past rows only when causal=True.
        return ...
```

`overlay=True` means the value belongs on the price chart. `overlay=False` means it belongs in a lower pane. Replay v1 plots overlays and displays point-in-time lower-pane values; dedicated shared lower panes are part of the later chart/drawing pass.

Built-ins now include SMA, EMA, RSI, ATR, session VWAP, Bollinger upper/middle/lower, MACD line/signal/histogram and ROC.
