# Research diagnostics and exports

Run Viewer → Trades exposes MFE (R), MAE (R), holding minutes and giveback.
Analysis → Excursion / trade management describes the complete run, not just
the displayed page or Trades filter. Existing analysis remains available.
No entry, exit, fill, sizing, cost or account rules are changed.

## Measurement definitions

- Initial price risk is `abs(entry_price - stop_loss)` from the recorded trade.
- MFE is the largest observed favourable price movement from entry divided by
  price risk. MAE is the largest adverse movement divided by price risk; both
  are nonnegative. Short trades mirror long trades.
- Giveback is MFE minus realised R, only when both measurements are finite.
  Realised R includes the engine's existing costs; price excursions do not
  independently model hypothetical exits or commissions.
- Holding minutes use recorded `minutes_in_trade`, otherwise elapsed UTC time
  between entry and exit. These are wall-clock minutes, not session minutes.
- Existing `mfe_r_lower_bound` / `mae_r_lower_bound` fields are normalized for
  display and CSV. Missing measurements display **—** and export empty cells.

New intraday and Gold reporting uses completed held one-minute bars and exact
entry/exit fills. Exit-bar extremes are excluded when exit ordering is unknown.
The entry bar is included only when the recorded setup establishes a market
entry at that bar's open; unknown or limit entry bars are excluded. A bar must
have completed by exit to contribute. No bars after exit are used. Thus these
are conservative lower bounds, not reconstructed tick paths. End-of-session
exits at a completed bar's close may use that fully held bar.

`mfe_price` / `mae_price` record the extremum price. Their timestamps and
`time_to_mfe_minutes` / `time_to_mae_minutes` identify the first observation
establishing that extremum. Bar observations use **bar timestamp + one minute**;
exact fills use their recorded timestamp. `time_to_0_25r`, `time_to_0_5r`,
`time_to_1r`, `time_to_1_5r`, `time_to_2r`, `time_to_3r` are elapsed minutes from
entry to the first observation proving the threshold was reached. These are
confirmation bounds, not exact intrabar crossing times. Unobserved thresholds
are null. Invalid/nonfinite/zero risk produces unavailable excursion fields.
Reporting happens after simulation and cannot feed strategy decisions.

Old saved runs are never backfilled or rewritten. Daily Momentum runs retain
their existing lower-bound measurements; precise new timing fields are absent.
Other strategies without recorded excursions remain unavailable. No migration
or automatic rerun is performed. Strategy version is blank if not recorded.

## Descriptive analysis

MFE and MAE buckets are lower-inclusive / upper-exclusive. Threshold cohorts
overlap and must not be added together. Percent measured uses the corresponding
MFE or MAE sample; final-R statistics exclude missing R. Exit percentages use
all trades in the cohort. PF is unavailable without a measured loss.
Timing, excursion and holding samples show their own N; N < 20 is labelled
low sample. A reversal count checks final R <= 0. The approximately -1R stop
count requires a stop exit and final R between -1.05 and -0.95 inclusive.

Closed-trade R drawdown requires valid exit timestamps and R for every trade;
simultaneous exits are netted together, starting from a zero R peak. It is
separate from account-percentage drawdown and does not measure intratrade
drawdown. Existing symbol/direction/session/exit/signal breakdowns also expose
excursion and holding averages with sample sizes. Legacy time-bucket diagnostic
extensions stay unavailable rather than guessing missing timezone context.

These are research data, not evidence of an edge or an optimal exit. No
threshold recommends a parameter change. Small samples are not conclusions.

## Exports

- Run Viewer exports all trades or all matching Trades-filter rows, even when
  only 20 are displayed. Core execution fields, normalized diagnostics, sorted
  scalar `meta_` columns and full `metadata_json` are retained.
- Full run JSON fetches the existing saved snapshot and configuration by ID.
  It does not rerun simulation. Unsaved results export the available snapshot.
- Journal Analysis keeps Export filtered CSV; Journal Trades adds Export
  matching trades CSV, using the backend-filtered/search/sorted report. Notes,
  source metadata, review fields and currencies are preserved.
- Manual Portfolio exports all holdings or all transactions independently;
  USD price fields and base currency remain explicit. Broker tables export
  only the selected account and record kind after table filtering/sorting.
  Export is disabled while loading or when the loaded snapshot does not match
  the selected account/kind. Currency fields and raw provider facts remain.
- Runs exports all locally matching loaded runs (the current list API loads
  at most 100). It does not claim to export the entire saved-run database.

Shared DataTable exports are optional (`exportable`, `exportFilename`, optional
`exportColumns` / `exportRow`). They use raw values, never cell renderers, and
run before pagination without changing selection or filters. UTF-8 CSV has a
BOM, escaped quotes/newlines, deterministic columns and JSON-encoded nested
values. Potential spreadsheet formulas are prefixed with an apostrophe;
negative numeric values remain numbers. Downloads revoke object URLs.

## Manual verification

1. Open an old saved run: absent diagnostics must show —. Open a newly run
   ORB/VWAP fixture: inspect MFE/MAE/hold/giveback and the lower-bound warning.
2. In Analysis, inspect bucket N, timing N, threshold reversals and R drawdown.
   Existing analysis and account drawdown must remain available.
3. Use a run with >20 trades. Filter by symbol/direction, export matching and
   all trades, and compare CSV row counts. Download full JSON and compare its
   saved `config` / `result` with the saved-run API response.
4. Filter Journal by ticker/search, export from Trades and Analysis; inspect
   multiline notes, custom reviews, currencies and nested source metadata.
5. Export manual holdings and transactions. In broker Portfolio switch
   account and kind, filter rows and export; ensure no other account/type is
   included and formatted currency strings have not replaced raw values.
6. Test a note starting `=SUM(A1)` and a negative numeric P&L in a spreadsheet:
   the note must remain text while P&L remains numeric.

## Verification and file manifest (2026-09-27)

Verification used temporary backend databases and mocked browser API responses,
not user databases or live providers.

- Focused backend: `python -m pytest tests/test_excursion_reporting.py
  tests/test_intraday_baselines.py -q -p no:cacheprovider` — **58 passed**.
- Full backend: `python -m pytest -q -p no:cacheprovider` with an isolated
  `--basetemp` — **523 passed**. One existing Starlette/httpx deprecation warning.
- Frontend: `node --test tests/*.test.js` — **68 passed**, including eight new
  diagnostic/export unit tests.
- Production: `npm.cmd run build` — passed; bundle-size advisory remains.
- `git diff --check` — passed (Git's existing LF/CRLF notices remain).
- Browser: `tests/browser/research-diagnostics.mjs` — passed Run Viewer legacy
  measurements, 45-row full / 30-row filtered exports, saved JSON equality,
  Journal filtered exports, Portfolio holdings / 35 transactions / 25 filtered
  positions, all activity types and account switching. No runtime exceptions.
  The excursion Analysis view had no page overflow at 1024 / 1440 / 1920px.

For the browser test, use an isolated Vite server and headless Chrome profile,
set `LEDGER_SMOKE_URL` and `LEDGER_CDP_URL`, then run
`node tests/browser/research-diagnostics.mjs`. The test replaces API fetches with
fixtures; it does not test live provider credentials or real broker data.

Modified application/documentation files:

- `backend/app/backtesting/intraday_reporting.py`
- `frontend/src/components/table/DataTable.jsx`
- `frontend/src/features/journal/AnalysisView.jsx`
- `frontend/src/features/journal/TradesView.jsx`
- `frontend/src/features/portfolio/BrokerPortfolioPanel.jsx`
- `frontend/src/features/portfolio/PortfolioPage.jsx`
- `frontend/src/features/portfolio/usePortfolioSnapshot.js`
- `frontend/src/features/strategy-lab/RunsTable.jsx`
- `frontend/src/features/strategy-lab/StrategyLabPage.jsx`
- `docs/BACKTEST_WORKFLOW.md`

New files:

- `backend/app/backtesting/excursion_reporting.py`
- `backend/tests/test_excursion_reporting.py`
- `frontend/src/features/strategy-lab/ExcursionAnalysis.jsx`
- `frontend/src/features/strategy-lab/tradeDiagnostics.js`
- `frontend/src/utils/csv.js`
- `frontend/src/utils/researchExports.js`
- `frontend/tests/researchExports.test.js`
- `frontend/tests/browser/research-diagnostics.mjs`
- `docs/RESEARCH_DIAGNOSTICS.md`

The pre-existing staged index was left untouched. Tests/builds also update
generated bytecode/Vite caches already tracked in this working tree; these are
not intentional source changes. No commit, migration or strategy/engine edit
is part of this update.
