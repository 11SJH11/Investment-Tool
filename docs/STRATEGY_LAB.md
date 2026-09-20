# Ledger Strategy Lab current contract

Ledger deliberately separates **strategy-owned trade logic/risk management** from **account/execution controls**.

A strategy plugin decides whether a setup exists and owns the trade-specific rules: entry intent, initial stop placement, target placement, breakeven rules, partial exits, trailing logic and discretionary exits. The common engine executes those instructions consistently and owns account sizing, session restrictions, fills, commissions, spread/slippage assumptions, P&L, R and analytics. That keeps one strategy from quietly using a more favourable simulator than another.

## Execution contract

- A strategy sees completed bars only.
- A market signal generated from a completed bar fills at the next primary-bar open. A limit signal waits for a subsequent bar to touch its original price, subject to configured expiry. Optional absolute entry deadlines are exclusive.
- Stops and targets are active after that fill, including the rest of the entry bar.
- A gap through a stop fills at the available opening price, not the stale stop price.
- A gap through a target fills at the available opening price.
- If the same OHLC bar touches both stop and target, the default is **stop first**. `target_first` is an explicit sensitivity test, not a claim that the target really happened first.
- Commission, assumed spread and slippage are explicit engine inputs.
- R is realised net P&L divided by initial risk at the actual fill.
- Planned R:R is target distance divided by stop distance at the actual fill.
- If overnight positions are disabled, open positions are flattened at the configured force-close time (or session end) with exit reason `session_close`.
- Any position remaining only because the dataset itself ends is closed with `end_of_data`.

This is an OHLCV simulator. It cannot reconstruct exact tick order, queue position, hidden liquidity, broker routing or an exact historical bid/ask spread unless those data are supplied separately.

## Trading schedule and guardrails

Engine-level filters are applied independently of strategy code:

- one or more allowed **entry windows** in New York exchange time;
- allowed weekdays;
- overnight yes/no;
- configurable forced-close time;
- maximum trades per day;
- daily realised loss limit in R;
- stop after N consecutive losses;
- cooldown in minutes after an exit;
- maximum simultaneous positions and aggregate leverage cap.

Entry windows control **new entries**. They do not automatically close an existing trade at the end of an entry window. Use the force-close setting when a strategy must be flat by a particular time.

## Sizing modes

The engine supports:

- risk % of account;
- fixed cash risk;
- fixed share quantity;
- fixed cash position value;
- position value as % of account.

Risk sizing is still constrained by available aggregate notional under the configured leverage limit.

## Diagnostic analysis

Every run returns descriptive breakdowns by:

- symbol;
- long vs short;
- entry hour (ET);
- weekday;
- month;
- exit reason;
- signal reason.

Each bucket reports trade count, win rate, average R, total R, R profit factor and net P&L. Ledger may surface observations such as which entry-hour bucket had the highest/lowest sample expectancy **only when a minimum sample exists**.

These observations are for hypothesis generation. They are not permission to optimise on the same data until the equity curve looks good. A later validation/out-of-sample workflow should be used before accepting a refinement.

## Trade audit

The result table includes **View chart**. Ledger fetches historical bars around that one simulated trade using the same symbol, timeframe and session path used by the backtester, then overlays:

- entry;
- initial stop;
- target;
- actual exit;
- entry/exit markers;
- strategy signal reason.

This is intended as a manual audit tool: inspect a sample of trades and check that the engine traded the rule you intended.


## Phase 5.3 chart-audit fixes

Performance-chart clicks resolve to the nearest **closed-trade event** on the time axis, so users do not have to hit the exact internal equity timestamp to open an audit.

Trade Audit context is count-based after session filtering. A request for 50 bars before a 09:35 ET regular-session entry therefore reaches into the previous trading day rather than subtracting 250 wall-clock minutes and losing premarket bars during regular-session filtering. The service widens the calendar request when needed, then returns the requested displayed-bar context.

## Adding a strategy

Drop one `.py` file into:

```text
backend/app/backtesting/strategies/
```

Modules are discovered automatically.

```python
from app.backtesting.models import EntrySignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry


@strategy_registry.register
class MyStrategy(Strategy):
    spec = StrategySpec(
        key="my_strategy",
        name="My strategy",
        description="My precise, testable rules.",
        timeframes=("5m", "15m"),
        defaults={"target_rr": 2.0},
        parameters=(
            ParameterSpec("target_rr", "Target R:R", "float", 2.0, 0.25, 10, 0.25),
        ),
    )

    def on_bar(self, ctx):
        bars_5m = ctx.bars("5m", count=20)
        bars_15m = ctx.bars("15m", count=20)
        ema = ctx.indicator("ema", timeframe="5m", length=20)

        if ctx.position is None and your_rules_are_true:
            stop = ...
            target = ...
            return EntrySignal(
                "long",
                stop_loss=stop,
                take_profit=target,
                reason="my_setup",
            )
        return None
```

The engine decides the actual next-bar fill and computes execution/accounting. Strategy code should not calculate broker fills or final P&L itself.

## Multi-timeframe no-lookahead behaviour

`ctx.bars("15m")` only returns 15-minute bars completed by the current decision time. An unfinished higher-timeframe candle remains invisible.

## Indicators

Indicators live in `backend/app/indicators/` and are discovered automatically. Built-ins include SMA, EMA, RSI, ATR, session VWAP and RTH volume-weighted population bands (rth_vwap_bands).

The same backend indicator implementations are used by Research overlays and Strategy Lab so formulas do not drift between frontend and backtester implementations.

## Why First Pullback and AMN are not pre-coded yet

Those models still contain discretionary terms that need explicit yes/no definitions: relevant swings, BOS, valid pullback, liquidity sweep, zone rules, catalyst requirements, retracement thresholds, exact entries, stops and targets. Ledger should not invent those definitions. Once agreed, they can be normal strategy plugins without changing the execution engine.

## Next serious research features

After the Phase 5.4 validation/management foundation, the next highest-value additions are:

1. precise First Pullback / AMN rule definitions and plugins;
2. walk-forward testing;
3. Monte Carlo sequencing/risk analysis;
4. richer scale-in handling and multiple independent exits;
5. Further Replay acceptance on the existing shared execution/Journal contracts;
6. shared persisted drawing tools and richer indicator chart UI.

## Phase 5.3 run/audit architecture

Backtest runs are persistent result snapshots. A run stores both its user-facing configuration and the deterministic result payload. Opening history must not silently re-run against changed data or changed strategy code; duplicating settings creates a new run instead.

Strategy plugins may attach point-in-time values through `EntrySignal.metadata`. The engine carries this metadata into the final trade so the audit UI can explain *why* a signal existed without re-evaluating the strategy after the fact.

Chart timestamps remain UTC in storage. Display timezone is a presentation concern; US-equity Strategy Lab views default to `America/New_York`.

### Future drawing model

TradingView-style drawings should be implemented as shared persisted chart objects rather than page-specific React state. The intended model is roughly:

```text
Drawing
- type (trend_line, horizontal_line, rectangle, text, fib, brush, ...)
- symbol
- timeframe / visibility rules
- anchor timestamps and prices
- style
- text / metadata
- workspace
```

Research, Replay and Trade Audit should consume the same drawing/indicator layer. This is intentionally not implemented as ad-hoc drawing code in Phase 5.3.

## Phase 5.4 — validation and position-management foundation

Phase 5.4 adds an explicit **Development → Validation → Out-of-sample** workflow. A validation suite freezes the current strategy/execution configuration and runs it across three non-overlapping date ranges. The three runs share an `experiment_group` and are persisted with their research role so they can be reopened later. A 60/20/20 split is a convenience default, not a statistical rule; users can choose the periods deliberately.

The Validation tab also includes a controlled **one-parameter sensitivity** sweep on development data. Ledger shows all tested values and does not automatically select the historical winner. The purpose is to look for robustness across nearby values rather than optimise to one peak.

Saved runs may now carry tags and an experiment-group identifier. The Runs tab surfaces grouped validation suites alongside ordinary side-by-side run comparison.

### Strategy-owned position management

A strategy may now return `ManagePositionSignal` in addition to `EntrySignal` and `ExitSignal`:

```python
from app.backtesting.models import ManagePositionSignal

return ManagePositionSignal(
    new_stop_loss=entry_price,   # e.g. move to breakeven
    reduce_fraction=0.5,         # close half of the remaining position
    reason="take_half_and_be",
    metadata={"management_stage": "one_r"},
)
```

Management decisions are made after a completed bar and become active at the **next primary-bar open**. A partial exit is a market-like execution subject to spread/slippage and commission. It remains part of the original logical trade: Ledger does **not** count a 50% scale-out as a second trade. The final trade stores a weighted average exit price, total fees/P&L, original planned stop/target, final managed stop/target, and individual partial fills in metadata.

This keeps the distinction clear:

- **strategy plugin**: setup, entry intent, initial stop/target, breakeven rules, partials, trailing logic;
- **engine/account settings**: how much capital is risked, leverage, trading window, commission, spread/slippage, account/session guardrails.

The engine regression suite exercises breakeven, partial-exit and trailing-stop primitives directly. The normal Backtest form does not ask the user to recreate a strategy's risk management on every run. Reference strategies keep their stop/target/management rules in their Python implementation; edit the strategy code when intentionally changing those rules.

### Performance trade markers

Performance charts now use explicit closed-trade markers. Clicking a marker opens that exact trade audit; clicking an arbitrary part of the equity line no longer jumps to a nearby trade. This removes the timestamp ambiguity that occurred with nearest-event selection.

## Phase 5.6 — multi-session Replay workspace

Replay now separates **historical context** from **future replay horizon**. A session can begin at a precise ET timestamp, include days/months of already-known historical context, and continue across later regular/extended sessions without stopping at the first closing bell. The service may load up to one calendar year per replay request; the UI still reveals bars only to the replay cursor.

Replay review has two cursors conceptually:

- the current visible cursor;
- the furthest historically revealed cursor.

Stepping backwards is allowed for review, but it marks the replay as having viewed future information. Orders are disabled while the view is behind the reveal frontier, and Journal notes record whether the replay remained clean or was rewound.

### Replay orders

Manual Replay supports market, limit and stop-entry intents. Market entries fill at the next revealed bar open. Limit/stop entries remain pending until the OHLC bar reaches the requested price; gap opens receive the bar open where that is the realistic first available price. Because bar data cannot establish all intrabar sequencing, same-bar stop/target handling remains conservative.

The user enters execution facts/intent (order type, position value, entry trigger where relevant, stop and target). Ledger derives initial risk and planned R:R from the eventual fill. These are analytics, never manual performance inputs.

### Replay indicator UI

Indicator plugins remain the calculation authority. Replay instances now store independent parameters, visibility, colour and line width. Generic plugin defaults are editable in the UI and sent to the shared backend registry. The UI uses a 12-colour default palette and permits multiple instances of the same indicator.

Dedicated lower panes, persisted chart drawings, draggable order lines, multi-chart layouts and the wider TradingView-style drawing/object-tree layer are intentionally later shared-chart work rather than page-specific hacks.


## Phase 5.6.1 — canonical intraday Replay data

Replay now treats 1-minute US-equity SIP bars as the canonical intraday source. The Replay service requests/caches 1m once and session-aligns 5m, 15m, 30m, 1h and 4h from those bars. This policy is intentionally Replay-specific: ordinary backtests still use the more economical provider-native cadence unless they specifically require a lower timeframe.

Changing Replay timeframe preserves the historical timestamp/reveal frontier and reloads the correct series atomically. It must never leave the UI labelled `1m` while still rendering 5m candles. Follow mode defaults off; the user can opt into auto-follow or make a one-off jump to the current candle.

Volume is registered in the shared indicator registry and participates in Replay's show/hide/remove UI. A dedicated pane system (including volume MA, RSI/MACD panes and pane sizing) remains part of the later shared chart layer.

## Current strategy release contracts

Frozen Gold v1.1 and Momentum/VCP rules remain unchanged. ORB/VWAP definitions
and limitations: ORB_VWAP_BASELINES.md. Gold filter experiments and all numerical
thresholds: GOLD_EXPERIMENTS.md. DXY-dependent variants explicitly reject missing
data and are not performance evidence. Runs comparison accepts up to 12 immutable
snapshots, reports sample sizes and missing values, and never ranks a winner.
Matched setup retention requires identical saved data/configuration fingerprints.
Older runs without those fingerprints remain readable; retention is unavailable.

Strategy Workspace: STRATEGY_WORKSPACE.md. Saving/editing performs no execution;
explicit trusted-code actions run in a separate process. Built-ins remain protected.
Dated futures economics and current continuous-execution restrictions:
FUTURES_FOUNDATION.md (historical checkpoint 3). Current front-alias execution,
roll safeguards and adjustment boundaries are in CONTINUOUS_FUTURES_RESEARCH.md.
