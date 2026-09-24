# Final RC verification

Date: 2026-09-23

This document records the automated/integration checks performed after the final Journal, drawing/Replay and Backtest workflow changes. It is a verification record, not a claim that the application is bug-free; final browser/provider behaviour still needs user-led manual testing on the target Windows environment.

## Frontend

### Unit/helper tests

Command:

```powershell
cd frontend
node --test tests/*.test.js
```

Result: **60 passed, 0 failed**.

Coverage includes Backtest workflow/run naming, table filtering/preferences, Journal analytics and multi-factor breakdowns, drawing geometry/cross-timeframe projection, chart request caching, Replay shortcuts/timeframe stepping, futures sizing, Journal timezone handling, Screener helpers and strategy-workspace helpers.

### Source parsing / import integrity

- **87** JavaScript/JSX source files parsed with the TypeScript parser.
- **0** source syntax errors.
- Local relative-import audit: **0 missing relative imports**.
- All browser acceptance `.mjs` files pass `node --check`.

Browser acceptance scripts were updated to match the final product behaviour:

- Replay timeframe controls are expected outside full screen.
- The removed `Current` Replay button must not reappear.
- Replay stepping checks no longer depend on the obsolete 1m-only `09:36` expectation.
- Opening a saved Backtest result must enter `Run Viewer`.
- The chart acceptance test checks that a drawing projected from 1m to 15m does not collapse an off-grid anchor to the chart's left edge, and confirms original stored market anchors survive the round trip.

### Production build limitation in this environment

`npm run build` could not be completed in the Linux execution container because the only available dependency tree originated from the user's Windows archive. Rolldown attempted to load `@rolldown/binding-linux-x64-gnu`, which is not present in that Windows dependency set. Network package installation is unavailable in this environment.

This is an environment/native-binding failure rather than a source parse failure. On the target Windows PC, run a clean install and build:

```powershell
cd frontend
Remove-Item -Recurse -Force node_modules -ErrorAction SilentlyContinue
npm ci
npm run build
```

The build must pass before treating the RC as release-ready.

## Backend

### Python compilation

```powershell
cd backend
python -m compileall -q app tools
```

Result: **passed**.

### Pytest

Tests not requiring DuckDB: **402 passed**.

The five DuckDB-related test files were then exercised separately:

- `test_continuous_execution.py`: **20 passed**, 6 blocked by missing `duckdb`
- `test_futures_foundation.py`: **32 passed**, 1 blocked by missing `duckdb`
- `test_massive_reference_cache.py`: **17 passed**, 1 blocked by missing `duckdb`
- `test_strategy_workspace.py`: **29 passed**, 1 blocked by missing `duckdb`
- `test_market_store.py`: **1 skipped** because `duckdb` is not installed

Combined backend result in this environment: **500 passing tests**, **9 tests blocked solely by `ModuleNotFoundError: duckdb`**, and **1 DuckDB-dependent skip**.

The blocked assertions should be rerun in the normal project virtual environment after `pip install -r requirements.txt`.

## API / data smoke checks

### Fresh empty data directory

A brand-new temporary `LEDGER_DATA_DIR` was created. The application initialised its schema and returned HTTP 200 for:

- `/api/health`
- `/api/journal/report`
- `/api/portfolio`
- `/api/screener/query`
- `/api/strategy-lab/runs`
- `/api/strategy-lab/jobs`

This checks that the final code still starts without relying on an existing user database.

### Synthetic demo database

With `LEDGER_DATA_DIR=../data/demo`, HTTP smoke checks passed for health, Journal report/options/playbook/daily reviews, Portfolio, Research, Screener query/technical status, saved Backtest runs, individual run loading and Backtest jobs.

Observed load sample:

- Journal report returned **1,211 trades** in about **0.6 s** in this container.
- 4 Playbooks available.
- Daily Review API returned its capped page of 120 records from the larger demo history.
- Portfolio returned 96 transactions.
- Research returned 160 items.
- Screener returned a 20-row page from its populated universe.
- 90 saved Backtest runs loaded and individual Run Viewer data was retrievable.

## Integration issues found during Step 4

Three issues were found during final review and fixed before packaging:

1. **Indicators navigation** — `Indicators` could be selected from Strategies but was omitted from the tab whitelist, causing an immediate fallback to Backtest. It is now a valid internal view.
2. **Broker connection placement** — Journal had already moved broker configuration to Settings, but Portfolio still duplicated the full connection panel. Portfolio now only shows snapshots/records and points users to Settings when no account snapshot exists.
3. **Portfolio auto-sync visibility** — removing the Portfolio connection panel also removed the polling callback that had incidentally refreshed broker snapshots. `usePortfolioSnapshot` now performs a lightweight local refresh every 60 seconds so backend auto-sync results still become visible while Portfolio remains open. This does not poll providers directly.

## Source-scope safeguard

The final package is produced from the Step 3 workflow checkpoint, not by replacing the project wholesale. Generated dependency/build folders are excluded, and no `.env` or credential file is included.

Compared with the user-uploaded pre-pass ZIP (excluding `.env`, dependency/build folders and Python caches):

- **259 files are byte-for-byte unchanged**
- **48 existing files changed**
- **8 files were added**
- **0 project files were deleted**

The changed set is concentrated in the explicitly scoped Journal/Analysis, chart/drawing, Replay, Backtest, Screener, shared-table/UI, demo-data and supporting test/documentation files.

## Manual acceptance focus

Before calling the app finished, manually exercise the areas where browser/provider behaviour matters most:

1. Draw rectangle/trend/fib on 1m, switch 5m → 15m → 1h → back to 1m; verify market anchors remain in the intended location.
2. Drag drawings within and across sessions; confirm no left-edge jump.
3. Replay on 1m/5m/15m/1h: Next, Previous and +5; confirm the selected timeframe advances as expected and trades still fill causally.
4. Journal Trades: create/review a trade, add a new custom reusable option, save, and confirm it is offered next time.
5. Journal Analysis: combine 2–4 dimensions, sort them, and verify sample counts remain sensible with multi-choice tags.
6. Calendar: move between months and open a busy day using the demo database.
7. Backtest: queue multiple symbols from the main input, verify the default `Run N` name, open the result in Run Viewer and inspect Summary/Trades/Analysis.
8. Delete/clear finished Backtest jobs and confirm saved Runs remain intact.
9. Screener: start the app with cached data, confirm results appear immediately, and observe background refresh without the table disappearing.
10. Portfolio: leave the page open across a broker auto-sync interval and confirm the snapshot updates without needing a connection panel there.
11. Run `npm run build` and the full backend suite in the normal Windows development environment with all requirements installed.

If those checks are clean, future changes should be treated as focused bug fixes or independently scoped add-ons rather than another broad workflow rewrite.
