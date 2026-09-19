# Checkpoint 11 - premium UX foundation

Status: completed from the existing working tree, after checkpoint 10 commit
`69278b1`. This checkpoint is presentation and descriptive Journal analytics.
It does not change strategies, engine accounting, Replay causality, market-data
routing, broker identity or order capabilities. No database/schema migration.

## Continuation audit

Already present when this continuation began: top navigation, full-width shell,
shared tokens, DataTable and view hook, compact Journal filters and summary,
Runs/comparison, Portfolio positions/activity tables, Calendar, Analysis charts,
Overview, Backtest secondary sections, and separate data hooks. These were kept.

Remaining work completed: old Journal/Runs preference migration; a single owner
for controlled table preference state; within-day Journal timestamp sorting and
full categorical options; zero-valued text filter consistency; Calendar account
selection with empty structured filters; earlier Playbook question-label fallback;
queue progress while collapsed; collapsed multiple-symbol input; corrected chip
and queue separators; explicit selected-month Calendar week labels. Added final
regressions and repeatable browser assertions, verified the current production
build, updated this handoff and the release index. No working feature was rebuilt
for stylistic preference.

## Architecture and behavior

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

## Preservation and checkpoint 10 status

Existing Journal reviews, broker facts, notes, screenshots, attachment slots,
Playbooks, Daily Reviews and IDs use unchanged storage. Migration/idempotency,
broker safety, engine, frozen Gold/Momentum/ORB/VWAP and Replay regressions are
included in the full backend suite. User databases/uploads/.env were untouched.

Checkpoint 10's real Massive NQ evidence remains in `RELEASE_CHECKPOINT_10.md`:
dated reference snapshots avoid duplicate undated contract pages; provider bars,
roll provenance and raw dated executions were verified. NQ tick 0.25, tick value
$5, point value $20 remain unchanged. This checkpoint exercised cached real
NQ data in saved/queued backtests and performed Charts/Replay shell regression;
it did not repeat external Massive downloads or claim fresh live-market parity.
Massive entitlement/quota/cold-cache latency and unverified TradingView parity
remain provider limitations. Workspace activation/deactivation and backend-owned
read-only auto-sync remain checkpoint 10 implementations, not new rewrites.

## Verification

Final commands (backend working directory for pytest):

```powershell
.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider --basetemp=C:/Users/jamie/Project/cp11-final-c
```

Full backend: **488 passed**, two existing Starlette/httpx/AnyIO deprecation
warnings. Includes **11 new Journal table-view cases**. Earlier continuation
run also passed 488; initial encoding and generated JSX syntax errors were fixed
before final verification.

Frontend working directory:

```powershell
node --test tests/*.test.js
npm.cmd run build
```

**39 passed, 0 failed**, including five new table/Calendar/preference cases.
Production build: **passed**, 88 modules, JS 747.15 kB (gzip 221.48 kB), CSS
51.77 kB (gzip 10.77 kB), 1.58s. Existing >500 kB bundle warning remains.
Repository `git diff --check`: passed.

## Browser acceptance

Isolated Chrome, temporary SQLite/uploads/Workspace, synthetic Journal and broker
fixtures; no real broker account writes or user-data mutations. Cached real
Massive NQ bars from checkpoint 10 support the fixture's saved/queued runs.

| Viewport | Pages checked | Layout result |
| --- | --- | --- |
| 1024 x 1000 | 13 | All pass; no page/main horizontal overflow |
| 1440 x 1000 | 13 | All pass; no page/main horizontal overflow |
| 1920 x 1000 | 13 | All pass; no page/main horizontal overflow |

The 13 pages are Overview, Backtest, Runs, Workspace, Journal Trades, Analysis,
Calendar, Daily Review, Playbook, Portfolio, Settings, Charts and Replay.
**39 page/viewport checks**, correct active navigation, **zero runtime exceptions**.
Charts/Replay checks are shell regression only. Screenshots were captured for
Trades, Backtest and Portfolio at all sizes and comparison; representative final
1024 Journal and 1440 Backtest screenshots were visually inspected.

Interactive assertions passed:

- Journal uncommon Account filter selects the 30 Acceptance trades. R > 0 gives
  N=10 and Total R=20. Density/filter/table mode survive reload; reset restores
  the full sample. All 21 columns remain accessible through internal scrolling.
- Populated and zero-result Analysis render without errors, with sample labels.
- Calendar shows daily/weekly results and opens 2026-09-03 / Acceptance Daily
  Review; saving succeeds.
- Portfolio displays GBP176 value, USD100 average cost/USD110 price, GBP160 cost,
  GBP16 unrealised P&L and 10% return for the synthetic holding. Note save/reopen,
  BUY orders and deposit IN labels pass.
- Workspace template save, trust, activation, immediate Backtest selection and
  deactivation pass in the isolated strategy directory.
- Two saved runs display comparison metrics and breakdowns. Runs header filter
  to zero matches, Reset view and compact density pass.
- Advanced execution expansion works; queued NQ backtest completes with a saved
  result. Playbook custom question save/reopen preserves its label.

Browser scripts are in `frontend/tests/browser/`. They are opt-in and require
an isolated fixture, not the user's normal app. They do save fixture reviews and
activate only the supplied trusted template. Required fixture: 30 manual trades
on account Acceptance across September 2026 (ten each R=-1/0/2), two trades on
September 3, at least two saved runs, and the documented synthetic broker holding.
The fixture server used here is `C:/Users/jamie/Project/cp11-smoke/server.py`;
CDP port 19240, HTTP port 18095, screenshots in that same temporary directory.
These local fixture/cache artifacts are not production dependencies or committed.

```powershell
$env:LEDGER_SMOKE_URL='http://127.0.0.1:18095'
$env:LEDGER_CDP_URL='http://127.0.0.1:19240'
$env:LEDGER_SMOKE_OUTPUT='C:/Users/jamie/Project/cp11-smoke'
node frontend/tests/browser/checkpoint11.mjs
node frontend/tests/browser/checkpoint11-extra.mjs
```

## Limitations and manual acceptance

- This is a first-pass foundation, not a replacement for ongoing real use.
  Large datasets are filtered in memory (Portfolio fetches all history pages);
  rendering is paginated, not virtualized. No large-history load benchmark.
- Desktop dark-theme acceptance was performed. Phone layouts, a full screen-reader
  audit and a complete light-theme visual sweep were not performed.
- Preferences are local to the browser. There is no cross-device saved-view sync.
- Calendar weekly summaries include only days in the selected month; this is
  explicitly labelled. Mixed-currency days with opposing signs stay neutral.
- Overview investments currently use broker snapshots; manual transactions remain
  on Portfolio. The old build checklist is no longer shown, but its local data
  was not deleted. Recent activity is a bounded summary, not an audit-event feed.
- Workspace remains trusted local Python execution, not a security sandbox.
  Auto-sync/quota coordination retains the single-backend-process limitation.
- No new strategy, live order execution, historical universe, data-provider swap,
  or TradingView parity claim was introduced.

Manual checklist:

1. Navigate all top-level pages; check active tab and full-width layout at your
   normal monitor size. Open Charts/Replay and confirm their existing controls.
2. In Journal, select Table, combine standard and + Filter dimensions, verify N/R
   and separate currencies, reload, choose all columns, scroll, and Reset view.
3. Review an imported trade and its older notes/images; confirm execution facts
   remain read-only. Save a manual review and a Playbook custom answer.
4. Inspect Analysis low-sample labels and empty results. Click a Calendar day,
   verify its date/account, save Daily Review and reopen it.
5. Check broker holding currencies, notes/details, BUY/SELL and cash direction.
   Confirm auto-sync status and explicit Sync now with your configured providers.
6. Queue a Backtest, navigate away and return; inspect Runs filters, Open/actions,
   select two runs and inspect comparison warnings and sample counts.
7. Save/test/activate a trusted unique Workspace strategy, confirm Backtest
   selection, then deactivate; verify the source remains available.

## Exact file inventory

The following files are relative to checkpoint 10 commit `69278b1`.

Modified (22):

- `backend/app/api/journal.py`
- `backend/app/core/journal_analytics.py`
- `docs/RELEASE_CHECKPOINTS.md`
- `frontend/src/app/App.jsx`
- `frontend/src/app/preferences.js`
- `frontend/src/app/uiPreferences.js`
- `frontend/src/app/useUIPreference.js`
- `frontend/src/features/dashboard/DashboardPage.jsx`
- `frontend/src/features/journal/AnalysisView.jsx`
- `frontend/src/features/journal/CalendarView.jsx`
- `frontend/src/features/journal/JournalFilters.jsx`
- `frontend/src/features/journal/JournalPage.jsx`
- `frontend/src/features/journal/JournalShared.jsx`
- `frontend/src/features/journal/TradesView.jsx`
- `frontend/src/features/portfolio/BrokerPortfolioPanel.jsx`
- `frontend/src/features/settings/SettingsPage.jsx`
- `frontend/src/features/strategy-lab/BacktestJobPanel.jsx`
- `frontend/src/features/strategy-lab/RunComparison.jsx`
- `frontend/src/features/strategy-lab/RunsTable.jsx`
- `frontend/src/features/strategy-lab/StrategyLabPage.jsx`
- `frontend/src/features/strategy-lab/runComparison.js`
- `frontend/src/styles/index.css`

New (16):

- `backend/tests/test_journal_table_views.py`
- `docs/RELEASE_CHECKPOINT_11.md`
- `frontend/src/components/TopNav.jsx`
- `frontend/src/components/insights/MetricCharts.jsx`
- `frontend/src/components/table/DataTable.jsx`
- `frontend/src/components/table/tableModel.js`
- `frontend/src/components/table/useTableView.js`
- `frontend/src/features/dashboard/useOverviewData.js`
- `frontend/src/features/journal/calendarModel.js`
- `frontend/src/features/journal/journalTable.js`
- `frontend/src/features/journal/useJournalData.js`
- `frontend/src/features/portfolio/usePortfolioSnapshot.js`
- `frontend/tests/browser/cdp.mjs`
- `frontend/tests/browser/checkpoint11-extra.mjs`
- `frontend/tests/browser/checkpoint11.mjs`
- `frontend/tests/table-view.test.js`
