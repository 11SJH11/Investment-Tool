# Ledger v2 architecture — Phase 5.3

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

Portfolio holdings are derived from BUY/SELL events rather than a second mutable holdings table. Historical market price / FX can resolve an amount-based transaction into shares, while an exact broker fill remains overridable.

## Journal source invariant

Every journal trade has one source:

```text
live_manual
paper_manual
replay
backtest
```

Source describes **where the execution facts came from**, not who performs the arithmetic. Whenever entry/exit/size/fees/stop are available, Ledger derives objective result, P&L and realised R consistently. Manual/broker records may use an explicit P&L override when FX, partial fills or broker charges make the simple calculation incomplete.

Backtest results are not automatically inserted into the manual Journal. Replay/broker sync can later create canonical journal records deliberately, preserving source separation for analytics.

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
Research / Strategy Lab / future Replay
                 ↓
          MarketDataService
                 ↓
        Parquet + DuckDB cache
                 ↓
              Alpaca
```

Research session handling and Strategy Lab both use New York session boundaries. This avoids maintaining two unrelated candle pipelines.

## Phase 5.4 / 5.4.1 research/management rules

- Backtest research roles (`development`, `validation`, `out_of_sample`) are persisted with immutable run snapshots. Runs created from one validation suite share an `experiment_group`.
- Parameter sensitivity is descriptive research. The UI deliberately returns the whole sweep and does not auto-select the best historical value.
- Strategy plugins own setup and trade-management intent. `ManagePositionSignal` can tighten/change protective levels and take a partial market-like exit at the next primary-bar open.
- Account sizing, leverage, entry windows, session guardrails, spread/slippage and commissions remain engine concerns.
- Partial exits do not create extra logical trades. Final P&L/R includes all partial fills and all commissions, while planned R:R remains based on the original stop/target.
