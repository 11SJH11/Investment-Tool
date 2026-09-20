# Ledger current architecture

## Product areas

Sticky top navigation: Overview, Charts, Replay, Backtest, Journal, Portfolio,
Research (Screener), Settings. Company research remains inside Charts.
Feature subtabs sit below global navigation. Data workspaces use available width;
readable forms may be narrower. Tables scroll internally.

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
  Backtest/Replay. Checkpoint 8 resolves front aliases to raw dated contracts,
  validates provenance and terminates open positions at a roll. Continuous
  schedules and dated OHLCV are cached separately; aliases are reconstructed.
- Strategy Workspace saves without execution, protects built-ins and runs
  explicitly trusted Python in a separate process. It is not a security sandbox.
- Frozen Gold and Momentum baselines; ORB/VWAP baselines; separate Gold filter
  experiments with immutable input/configuration fingerprints and saved comparison.
  DXY-dependent experiments explicitly report unavailable data, not a proxy.

Current contracts: FUTURES_FOUNDATION.md, STRATEGY_WORKSPACE.md,
ORB_VWAP_BASELINES.md, GOLD_EXPERIMENTS.md and BROKER_CONNECTIONS.md.

## Checkpoint 9 — backtest jobs and frontend foundations

`BacktestJobs` is a durable SQLite-backed queue with a bounded in-process thread
pool (default two). The new `/strategy-lab/jobs` routes submit independent jobs,
list progress, request cancellation and explicitly retry failures. Workers call
the existing BacktestService; the engine adds only an optional observation/
cancellation callback. Accounting and frozen strategy rules are unchanged.
Successful results still use BacktestRunRepository. A queue-job identity in the
immutable configuration allows startup recovery across the save/status boundary.

MarketDataService serializes provider/cache preparation through process-wide
reentrant locks keyed by cache root and provider. Continuous-to-dated recursive
loads share the lock; ordinary missing-range requests deduplicate through coverage.
Run one backend process per data directory. See BACKTEST_WORKFLOW.md for restart,
cancellation, legacy synchronous API and trusted Workspace limitations.

Frontend operational state lives in `useBacktestJobs`; deterministic payload,
summary and filtering transforms live in `backtest-workflow.js`. `RunsTable` and
`BacktestJobPanel` present those results. `uiPreferences`/`useUIPreference` store
presentation preferences only. `components/ui.jsx` supplies reused Button, Panel,
Section, TabBar, PageToolbar, FormGrid, MetricGrid and MetricCard primitives.

The existing theme palette remains the source for surface/text/border tokens.
New surface/accent/positive/negative aliases, spacing steps, radii and control-height
tokens support shared primitives and existing color adapters. This is a focused
foundation, not a full app redesign or a change to the chart library.

## UI and presentation contracts


- `TopNav` preserves route keys and dirty-navigation guards, exposes active-page
  semantics and a skip link. Overview, Charts, Replay, Backtest, Journal,
  Portfolio, Research and Settings use the sticky global header. Feature tabs
  remain below it. Existing navigation order preferences are retained.
- The common app workspace fills available width with 20-32px responsive outer
  padding. Data tables scroll internally; Charts/Replay keep their own controls.
- Shared CSS extends existing light/dark tokens for surfaces, borders, semantic
  colors, spacing, typography, radii, control sizes and compact table density.
- `DataTable`, `tableModel` and `useTableView` supply compact/comfortable density,
  sticky headers/key column, column visibility/order, categorical search and OR
  selection, numeric strict greater/less and inclusive ranges, date ranges,
  text search, sorting, row selection, primary action plus secondary menu, 50-row
  pagination, removable chips and Reset view. Runs and Portfolio filter locally;
  Journal submits the same standard rules to its authoritative backend report.
  The old Runs helper remains for compatibility tests, but no old Runs filter UI
  or separate feature-specific table filter implementation is mounted.
- Journal retains all 22 uncommon structured dimensions through + Filter, named
  saved views, shared date/timezone rules and AND across fields. Backend filtering
  precedes summary/calculation, so all matching rows contribute, not just the
  displayed page. Money stays separated by currency. Primary metrics are Net
  P&L, Total R, win rate and R profit factor; secondary metrics include N/outcomes,
  average R/winner/loser/holding time; diagnostics are expandable.
- Analysis adds entry-hour/10-minute/30-minute buckets, weekday/time heatmap,
  session, strategy/Playbook, setup, direction, month and process breakdowns.
  Cumulative R, drawdown and rolling last-20-recorded-R expectancy use closed
  trades in close order. N and low-sample labels accompany descriptive results;
  no automatic trading rule, causal conclusion or winner is generated.
- Calendar uses entry dates in the Journal timezone, subtle positive/negative/
  neutral treatment, per-day P&L/R/N, selected-month weekly totals and inline
  day details. Daily Review receives the selected date and unique account where
  available; ambiguous multi-account selection leaves the existing Main default.
- Portfolio retains account summary cards, puts positions/orders/cash into the
  common table, separates instrument and wallet currencies, and exposes notes,
  tags and raw provider facts on demand. BUY/SELL and cash IN/OUT use checkpoint
  10 provider semantics; missing/ambiguous facts remain unavailable.
- Runs uses compact rows, Open plus an actions menu, full-width filters and
  selection for comparison. Comparison has a metric grid, R/expectancy/drawdown/
  trade-count charts, sample counts and existing fingerprint/retention warnings.
  Independent run returns are never summed or ranked.
- Backtest retains the normal workflow with secondary validation/sensitivity
  sections. Multiple-symbol entry, advanced execution, costs, account limits,
  schedule and additional strategy parameters are collapsible. Jobs retain
  queue actions and progress with a compact collapsed summary.
- Overview replaces the development checklist with a 30-calendar-day Journal
  summary, separate broker investment snapshots, research/job status and recent
  runs/trades. Missing source data is labelled unavailable; no synthetic product
  values are inserted. `useOverviewData`, `useJournalData` and
  `usePortfolioSnapshot` keep fetching outside presentation.
- Presentation state uses browser-local `ledger.ui.*` keys. Older Journal column
  selections and Runs filters/sort/columns are read if no new view exists. New
  views take precedence. Reset restores that table's columns/order/filter/sort/
  density; Journal reset also clears structured filters, view mode and expanded
  diagnostic statistics. It never removes trading records or configuration.
  Named saved views remain available after resetting the current view.


## Checkpoint 12 workflow and data paths

`WorkflowContext` carries ticker, compatible timeframe and explicit timestamps
between Screener, Charts, Backtest, Replay and Journal. New York session dates
are derived from UTC handoffs. Handoffs configure views; they never execute trades.
`chartRequests` deduplicates pending chart requests and caches completed responses
for 15 seconds (32 entries). Explicit refresh bypasses reuse. `chart-data` fetches
one prepared frame for all requested registered indicators; old GET APIs remain.
Screener background refresh reads only local daily Parquet caches, stores additive
`technical_snapshots`, and queries validated SQL expressions. It is a current
universe discovery service, not a point-in-time historical universe.
Replay playback and ticket presentation are separate modules. Canonical reveal,
fill, roll and Journal identity behavior remain in the existing Replay path.
