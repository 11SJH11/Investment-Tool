# Ledger current architecture

## Product areas

1. Dashboard
2. Screener ✅
3. Research ✅
4. Markets
5. Portfolio ✅
6. Journal ✅
7. Strategy Lab ✅ backtest foundation
8. Settings

## Layering rule

```text
React feature
    ↓
FastAPI router
    ↓
feature service
    ↓
repository / shared data service
    ↓
provider or local storage
```

Routers remain thin and React never calls Alpaca/SEC/FRED directly.

## Portfolio model

Manual Portfolio holdings derive from BUY/SELL events. Trading 212 account snapshots and history use separate broker-owned facts plus editable notes/tags; snapshots are not counted again as manual buys. Provider/account/environment identities and atomic sync cursors prevent duplicate import. See BROKER_CONNECTIONS.md.

## Journal source invariant

Every journal trade has one source:

```text
live_manual
paper_manual
replay
backtest
broker_oanda (and registered future broker adapters)
```

Source identifies the origin of execution facts. Manual and Replay facts use the
common execution calculations; broker-imported facts and provider P&L are read-only.
Discretionary review remains editable, and resync preserves it. Replay closed
trades automatically enter this same Journal using deterministic external IDs.
Backtests remain immutable saved research snapshots, not automatic Journal rows.
Playbook custom fields, Daily Review, notes and attachments share stable IDs.
Broker profiles support separate accounts/environments; Tradovate is unsupported.

## Strategy Lab invariant

```text
Strategy plugin
    ↓ EntrySignal / ExitSignal
BacktestEngine
    ↓ fills / sizing / risk / fees / slippage
Canonical simulated trades + metrics
```

Strategy plugins do not implement their own broker simulator. The common engine owns execution assumptions so two strategies can be compared under the same rules.

`StrategyContext` is point-in-time. Higher-timeframe bars are exposed only after completion, preventing a 5m strategy from reading an unfinished 15m/1h candle.

Strategy modules are automatically discovered from `backend/app/backtesting/strategies/`. Indicators are automatically discovered from `backend/app/indicators/`.

## Shared indicator rule

The same registered indicator calculation must power Strategy Lab and Research overlays. A causal indicator may opt into full-frame caching for speed only when `value[t]` cannot depend on future rows. Custom indicators default to the safer non-cached point-in-time calculation.

## Notion template mapping

The exported Notion Journal informed the Journal model:

- Account, DXY, Entry, Entry TF, Market Condition, Pair, Position, R, Setup, TF Align, TF Type and Wick map to structured fields;
- redundant Win/Loss/B/E columns become one derived result;
- 1m/5m/15m/30m/1H/4H sections become timeframe notes plus image slots;
- Analysis / Entry / Management / Learning remain dedicated fields;
- Daily Review is separate;
- setup reference material belongs to Playbook.

## Media

`media_attachments` stores metadata; image bytes live under the gitignored `backend/data/uploads/` directory.

## Shared market-data path

```text
Charts / Strategy Lab / Replay
                 ↓
          MarketDataService
                 ↓
        Parquet + DuckDB cache
                 ↓
    Alpaca / OANDA / Massive
```

Research session handling and Strategy Lab both use New York session boundaries. This avoids maintaining two unrelated candle pipelines.

## Phase 5.4 / 5.4.1 research/management rules

- Backtest research roles (`development`, `validation`, `out_of_sample`) are persisted with immutable run snapshots. Runs created from one validation suite share an `experiment_group`.
- Parameter sensitivity is descriptive research. The UI deliberately returns the whole sweep and does not auto-select the best historical value.
- Strategy plugins own setup and trade-management intent. `ManagePositionSignal` can tighten/change protective levels and take a partial market-like exit at the next primary-bar open.
- Account sizing, leverage, entry windows, session guardrails, spread/slippage and commissions remain engine concerns.
- Partial exits do not create extra logical trades. Final P&L/R includes all partial fills and all commissions, while planned R:R remains based on the original stop/target.

## Current release capabilities

- Journal V2: multi-select filters, cards/table, custom Playbook review fields,
  Daily Review, Analysis/Calendar, timezone handling and currency-separated totals.
- Replay clips canonical 1m bars before aggregation and indicators. Partial bars
  contain revealed data only; timeline navigation never exposes future OHLCV.
- Dated futures use tick size, point value, multiplier and whole contracts in
  Backtest/Replay. Continuous aliases remain chart-only until checkpoint 8.
- Strategy Workspace saves without execution, protects built-ins and runs
  explicitly trusted Python in a separate process. It is not a security sandbox.
- Frozen Gold and Momentum baselines; ORB/VWAP baselines; separate Gold filter
  experiments with immutable input/configuration fingerprints and saved comparison.
  DXY-dependent experiments explicitly report unavailable data, not a proxy.

Current contracts: FUTURES_FOUNDATION.md, STRATEGY_WORKSPACE.md,
ORB_VWAP_BASELINES.md, GOLD_EXPERIMENTS.md and BROKER_CONNECTIONS.md.
