# Checkpoint 9 — final handoff

Checkpoint 8 was completed first and committed as `19daef5`, with 454 backend
tests, 22 frontend utility tests and the production build passing. Its complete
handoff is in RELEASE_CHECKPOINT_8.md. TradingView/real-provider parity remains
unverified because no real comparison exports were supplied.

## Delivered behavior

- Primary Backtest navigation: Backtest, Runs, Strategies, Workspace. Indicators
  remain available from Strategies; Replay remains available in its own workspace.
- Single / Validation / Sensitivity modes, progressive configuration sections,
  visible strategy-owned risk information, and a submission summary reflecting
  base configuration. Invalid sizing is blocked in the queue UI. Requested dates
  are explicitly distinguished from the provider-capped actual saved end.
- Persistent SQLite jobs, two workers by default, explicit preparation/running
  states, actual simulation event progress, cancellation and explicit failed retry.
- Paste/search/watchlist selection creates one independent account/job/run per
  symbol. Validation groups remain separate per symbol. Batch counts, cancel,
  result opening and immutable comparison are available while configuring more work.
- Runs table category checkboxes, text search, numeric sort/greater/less/between,
  date ranges/order, visible columns and up to 12 selected comparisons. Win rate
  and profit factor are read from existing immutable result JSON, without migration.
- Nine-step Workspace guidance and plugin API explanation preserve trusted local
  Python protections. No frozen strategy, broker import or chart semantics changed.
- Shared Button, Panel, Section, TabBar, PageToolbar, FormGrid, MetricGrid and
  MetricCard primitives; theme surface/accent/result-color aliases, spacing/radii/
  control-height tokens. Scope is Backtest/Strategy Lab, not a whole-app redesign.
- Shared local presentation preferences persist run type, section expansion,
  Runs view/columns/filter/sort and result chart mode. Journal cards/table did not
  previously persist; that narrow preference now uses the same helper. Existing
  Journal column preferences and behavior are otherwise retained.

## Schema, execution and provider protection

One additive `backtest_jobs` table is created idempotently on queue initialization:
UUID ID, request key, ordinal, batch ID, JSON payload, state, processed/total events,
run ID, safe error, cancellation flag, created/updated timestamps; unique request
key + ordinal. No existing table, user ID or historical result is rewritten.

Jobs reuse BacktestService and save through BacktestRunRepository. The only engine
change is an optional callback every 64 timestamp events, permitting observation
and cooperative cancellation. Trading accounting is unchanged. A queue-job ID in
the immutable run configuration permits recovery if the process stops between
saving the result and recording job completion. Cancellation and saving are mutually
exclusive under the queue lock.

Queued jobs resume on startup. Interrupted active jobs require explicit retry,
unless their saved result already exists, in which case completion is recovered.
Graceful shutdown cancels active work cooperatively and leaves queued work intact.
Requests with the same idempotency key return the existing jobs; a different payload
under that key is rejected. Raw provider exception text is neither stored nor logged
by the queue, preventing accidental credential/URL exposure through job errors.

`MAX_CONCURRENT_BACKTESTS` accepts 1–8, default 2. The thread pool is process-local.
MarketDataService uses shared reentrant provider/cache-root locks around freshness
probes and cache read/fetch/merge operations. Waiting requests recheck coverage, so
identical missing-range requests fetch once. Different providers can prepare data
independently; simulations can overlap after preparation. Existing provider retry,
backoff and reference caches remain intact, including recursive continuous-futures
to dated-contract loading.

## Final automated verification

Run against the final implementation, using isolated test data:

| Check | Exact result |
| --- | --- |
| Full backend suite | **465 passed**, 2 existing dependency deprecation warnings, 57.31s |
| Focused queue + shared market-data tests | **12 passed**, same 2 warnings, 3.44s |
| All frontend utility tests | **33 passed**, 0 failures, 220.53ms |
| Production build | **passed**, 79 modules, 1.65s |
| Final whitespace/diff check | passed |

Exact commands, from their indicated directories:

```powershell
# backend/
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=C:\Users\jamie\Project\cp9-final-full
.venv\Scripts\python.exe -m pytest tests/test_backtest_jobs.py tests/test_market_data_service.py -q -p no:cacheprovider --basetemp=C:\Users\jamie\Project\cp9-final-focused
# frontend/
node --test tests/*.test.js
npm.cmd run build
# repository root
git diff --check
```

The full suite includes the frozen XAU and Momentum, engine, Replay integrity,
continuous-futures, broker/Journal, Workspace and migration/preservation tests.
Eleven new backend test cases cover lifecycle/concurrency/cancel/failure/idempotency,
restart recovery, provider deduplication across Alpaca/OANDA/Massive keys, real-engine
result equivalence, API validation and configuration bounds. Eleven new frontend
tests cover modes, sizing validation, symbols/batch isolation, summary, filters,
queue counts and persistence; the prior 22 tests also pass.

The initial test invocation encountered an inaccessible default pytest temp folder;
the runs above used fresh isolated writable basetemp paths. The first broad run
also found a minimal fake provider without a `key`; the lock now uses a safe type
fallback. The affected focused tests and final full suite were rerun successfully.
The build retains its existing >500 kB JavaScript chunk warning (728.33 kB output,
214.27 kB gzip); no dependency or bundler refactor was introduced.

## Browser/manual checks actually performed

Isolated headless Chrome, production assets, temporary SQLite/cache/workspace data,
synthetic VWAP daily session bars; all external provider HTTP blocked. A fixture
gate held simulation workers to make waiting/concurrency observable.

1. Submitted an AAPL VWAP run; configured and submitted another while it was running.
2. Queued an AAPL/MSFT/NVDA batch: exactly **2 running + 3 queued**, then all **5 completed**.
3. Observed exactly **3 provider fetches total**, one per symbol; all three AAPL jobs
   reused one cache fetch. The third worker did not start while the first two were held.
4. Opened a completed immutable result and changed the performance view.
5. Selected multiple saved runs and opened their comparison.
6. Verified Validation/Sensitivity controls switch without exposing the other mode's
   experiment controls; selected mode survived reload.
7. Verified expanded Costs, Runs symbol/numeric filters, column selection and sorting
   survived reload/navigation. Journal Table selection also survived reload.
8. Verified all nine Workspace guidance steps and trusted-code warning.
9. Final Backtest, Runs and Journal checks measured **1024px viewport / 1024px page
   scroll width**, with internal table scrolling and **zero browser runtime errors**.

Browser harness issues encountered during setup (restricted Chrome startup,
reload timing and duplicate injected fetch shims) were corrected in the isolated
test harness. The final complete smoke/persistence passes had no runtime errors.
Real-account connectivity, live provider quotas and TradingView price parity were
not tested; no user database, real credentials or broker orders were touched.

## Known limits and next step

- One application process per data directory; no distributed/multi-Uvicorn-worker
  queue ownership. Threads do not promise CPU speedup for GIL-bound strategies.
- Cancellation waits for the next cooperative boundary; it cannot interrupt an
  in-flight provider request or arbitrary strategy Python. Commit completion wins
  over a late cancel. Unexpected provider errors use intentionally generic safe text.
- The queue view returns the latest 500 jobs; saved Runs keeps its existing UI/API
  limits. No automatic pruning. Deleting a saved run can leave its old job link empty.
- Workspace trusted execution and the legacy synchronous API retain their separate
  paths; their work is not counted against the new queue worker limit.
- Independent symbol tests are not a portfolio/universe simulator. Survivorship,
  point-in-time-universe and continuous-provider parity limitations are unchanged.
- UI preferences are local to this browser; actual strategy configuration is not
  saved as a presentation preference. Explicit force-refresh intentionally refetches.

Recommended next UI tab: **Journal**, using these primitives and persistence patterns
while preserving broker facts, media and review workflows. That redesign has **not**
been started. See BACKTEST_WORKFLOW.md for the acceptance walkthrough and architecture
details. Checkpoint 9 is the stopping point.

## Exact file inventory

The inventory below is relative to checkpoint 8 commit `19daef5`.

### Changed files

- `backend/.env.example`
- `backend/app/api/strategy_lab.py`
- `backend/app/backtesting/engine.py`
- `backend/app/core/config.py`
- `backend/app/services/backtest.py`
- `backend/app/services/container.py`
- `backend/app/services/market_data.py`
- `backend/app/storage/backtest_run_repository.py`
- `docs/ARCHITECTURE.md`
- `frontend/src/api/client.js`
- `frontend/src/features/journal/TradesView.jsx`
- `frontend/src/features/strategy-lab/StrategyLabPage.jsx`
- `frontend/src/features/strategy-lab/StrategyWorkspace.jsx`
- `frontend/src/features/strategy-lab/ValidationPanel.jsx`
- `frontend/src/styles/index.css`

### New files

- `backend/app/services/backtest_jobs.py`
- `backend/tests/test_backtest_jobs.py`
- `docs/BACKTEST_WORKFLOW.md`
- `docs/RELEASE_CHECKPOINT_9.md`
- `frontend/src/app/uiPreferences.js`
- `frontend/src/app/useUIPreference.js`
- `frontend/src/components/ui.jsx`
- `frontend/src/features/strategy-lab/BacktestJobPanel.jsx`
- `frontend/src/features/strategy-lab/RunsTable.jsx`
- `frontend/src/features/strategy-lab/backtest-workflow.js`
- `frontend/src/features/strategy-lab/useBacktestJobs.js`
- `frontend/tests/backtest-workflow.test.js`
