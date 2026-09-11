# Ledger strategy plugin template

A strategy plugin owns the setup and its trade management. The generic run form owns account sizing, costs, trading schedule and account/session guardrails.

Create a new Python file under `backend/app/backtesting/strategies/`. The package auto-discovers modules, so there is no central strategy switch statement to edit.

```python
from app.backtesting.models import EntrySignal, ExitSignal, ManagePositionSignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry


@strategy_registry.register
class MyStrategy(Strategy):
    spec = StrategySpec(
        key="my_strategy",
        name="My Strategy",
        description="Objective description of the setup.",
        defaults={"lookback": 20},
        timeframes=("5m", "15m"),
        parameters=(
            # Normal run-to-run strategy inputs only.
            ParameterSpec("lookback", "Lookback", "int", 20, 5, 100, 1),
        ),
        research_parameters=(
            # Hidden from ordinary runs. Validation/sensitivity may temporarily
            # override these without changing the source default.
            ParameterSpec("target_rr", "Target R:R", "float", 2.0, 0.5, 5.0, 0.25),
        ),
        risk_management={
            "Initial stop": "Defined by the setup",
            "Initial target": "Defined by the setup",
            "Management": "Defined by the setup",
        },
        source_file="backend/app/backtesting/strategies/my_strategy.py",
    )

    def on_bar(self, ctx):
        bars_5m = ctx.bars("5m", count=100)
        bars_15m = ctx.bars("15m", count=50)
        ema = ctx.indicator("ema", timeframe="5m", length=20)

        if ctx.position is not None:
            # Optional strategy-owned management. Any instruction returned here
            # is applied on the next primary-bar open.
            # return ManagePositionSignal(new_stop_loss=..., reduce_fraction=0.5)
            return None

        # Only information completed at ctx.current_time is available.
        if YOUR_OBJECTIVE_ENTRY_RULE:
            entry_reference = float(ctx.current_bar["close"])
            stop = ...
            target_rr = float(self.params["target_rr"])
            risk = abs(entry_reference - stop)
            target = entry_reference + risk * target_rr
            return EntrySignal(
                "long",
                stop_loss=stop,
                take_profit=target,
                reason="my_entry_reason",
                metadata={"why": "values needed for Trade Audit"},
            )
        return None
```

## Rules

- Do not fetch data directly inside a strategy. Use `StrategyContext`.
- Never inspect bars that have not completed yet.
- Entry signals created after a completed candle fill at the next primary-bar open.
- Put stop/target/breakeven/partial/trailing logic in the strategy when those rules are part of the setup.
- Put position size, account risk, commission, spread, slippage, leverage and account guardrails in backtest configuration.
- Attach objective signal metadata so Trade Audit can explain exactly why the strategy entered.
- Use `research_parameters` only for robustness/sensitivity experiments; normal runs keep those rules strategy-owned.
