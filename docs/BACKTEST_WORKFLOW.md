# Backtest workflow

## Configure a backtest

For Run Viewer excursion measurements, analysis and CSV/JSON exports, see
[Research diagnostics and exports](RESEARCH_DIAGNOSTICS.md).

The primary tabs are **Backtest, Runs, Strategies**. Indicators remain
available from Strategies. The standalone Replay workspace is unchanged.

Select a strategy, symbols, requested dates, primary timeframe, balance, sizing,
name and optional tags. Ordinary runs use the internal development role; validation
assigns explicit roles. Review **Ready to run** before submitting. Auto session
resolves separately for each instrument in an independent batch. The requested
end date is still capped by the existing historical-delay/provider-availability
rules; the saved result records the actual end. Invalid zero/negative account
amounts are blocked in the new UI rather than silently invoking engine defaults.

Execution, costs, account limits, schedule, guardrails and strategy parameters
are expandable. Strategy-owned stop/target information remains visible. Saved
section preferences do not change the actual trading configuration.

### Single backtest

One symbol creates one job. Multiple selected symbols create an explicitly labelled
independent batch. Paste comma/space/semicolon/newline-separated symbols, use the
existing watchlist checkboxes, search, or remove individual chips. Each symbol
gets the same initial account balance and base configuration. Returns are **not**
combined into portfolio performance. The queue accepts 1–100 jobs per submission,
with exactly one symbol in each job. The older synchronous API still supports its
existing shared-capital multi-symbol behavior; this UI never switches to it silently.

### Validation & out-of-sample (expandable)

Choose non-overlapping development, validation and out-of-sample dates, an
experiment name and notes. All periods use the same base strategy/configuration.
Each symbol has its own experiment group. Submission immediately queues the jobs;
the form stays available. The live summary shows the first submitted symbol;
all completed symbols/periods remain accessible in Runs and batch comparison.
Opening a saved experiment reads immutable snapshots, without rerunning it.

### Sensitivity analysis (expandable)

Spectrum and interaction research define exact numeric values or bands and run
independent simulations from the selected configuration. No winner is selected
and source defaults are never tuned automatically. See [Research experiments](RESEARCH_EXPERIMENTS.md)
for the authoritative execution, grid, limits, fingerprint and resume contracts.

## Queue and concurrency

- States: queued → preparing data → running → completed; failure/cancellation are
  terminal alternatives. Completed jobs link to immutable BacktestRunRepository runs.
- The persisted compute setting selects an application-wide CPU reservation budget.
  Ordinary simulations and research process pools share it; parent jobs cannot
  multiply it. Preparation/coordinator threads are separate from reserved CPU slots.
  The queue shows configured budget, reserved workers and waiting simulations.
  This is one application process, not a distributed limit across servers.
- Data preparation has no invented percentage.
  Simulation reports actual processed/total primary timestamps every 64 events.
  This is simulation progress, not an estimate of remaining wall time.
- Cancel queued items individually or together. Running cancellation is cooperative:
  checked around data loading, every 64 simulation events, and before committing.
  An in-flight HTTP request, strategy callback or report calculation is not forcibly
  killed. Once the immutable save starts under the commit lock, it completes; a
  later cancellation cannot erase a saved result.
- Each submission has a unique request key and per-job ordinal. Retrying the same
  request key returns the same jobs; conflicting payloads are rejected. Polling,
  navigation and refresh never submit jobs. Failed-item retry is an explicit new job.
- Batch counts, completed-result opening, queued cancellation, failed retry and
  comparison of up to 12 completed results are available in the queue panel.

### Persistence and restart

The additive `backtest_jobs` SQLite table stores request identity, payload, batch,
state, progress, result ID, cancellation flag and timestamps. Existing data/IDs and
saved results are not rewritten. Startup resumes jobs still queued. Interrupted
preparing/running jobs become failed and require explicit retry, unless an immutable
run already exists with the matching `config.queue_job_id`; that save is recovered
as completed without rerunning. Graceful shutdown cooperatively cancels active work
and leaves queued jobs for the next startup.

Run **one backend application process** against a data directory. This is not a
distributed queue and does not support multiple Uvicorn worker processes sharing
the queue. The list endpoint exposes the latest 500 jobs; run history retains its
existing 100-row UI / 500-row API retrieval limits. There is no automatic retention
deletion. Deleting a saved result can leave its completed job link without a result.
Workspace trusted-code execution and the legacy synchronous API retain their
existing execution paths; the queue worker bound applies to queued jobs.

## Shared data protection

Jobs reuse BacktestService → MarketDataService → shared coverage/Parquet caches.
A process-wide reentrant lock per provider and cache root serializes coverage
inspection, missing-range fetch, merge and read. Identical requests recheck coverage
after waiting, so only the first fetches missing bars. Optional freshness probes use
the same lock and existing provider caches. Different providers can prepare data
independently; simulation can overlap once its data is ready. Existing retry/backoff,
rate limits and contract-reference caching remain in place.

Reentrant locking also covers continuous-futures reconstruction calling back into
dated-contract loading. Roll/reference caches and raw execution provenance remain
unchanged. Explicit force-refresh requests intentionally refetch; protection is
process-local, not a cross-process distributed lock.

## Runs and saved views

The table shows status, strategy, symbol, requested period, role, trades, win rate,
average/total R, profit factor, return, max drawdown and creation date. Optional
columns include tags, experiment and timeframe. Headers support category checkboxes,
text search, numeric sorting and strict greater/less or inclusive between filters,
plus date ranges/order. Select up to 12 runs for the existing immutable comparison.
Failed/queued jobs are shown in the queue, not fabricated as saved result rows.

`ledger.ui.*` local storage remembers run type, expanded sections, visible columns,
sort/filter/view and result chart mode. Journal cards/table now uses the same
presentation-preference helper; its existing column preferences are preserved.
Job execution state stays on the server. Strategy configuration and unsaved code
are not silently persisted as presentation preferences. Storage failure falls back
to usable defaults.

## Strategy files

Add/edit local Python strategies, then use **Strategies > Refresh strategies**.
See [manual refresh](STRATEGY_REFRESH.md) for validation, active-job safety and
saved source fingerprints. Workspace is hidden from the normal frontend; backend
source/history remains intact.

## Acceptance walkthrough

1. Choose VWAP, AAPL, a period with data, and review sizing/costs. Run it.
2. While it executes, change the name and queue another; the form stays editable.
3. Paste AAPL/MSFT/NVDA. Queue three independent runs; CPU reservations obey the configured budget.
4. Cancel a queued item, open a completion, and compare completed snapshots.
5. Expand Validation & out-of-sample or Sensitivity analysis within the normal workflow.
6. Filter Runs by symbol/role, numeric boundaries and dates. Select two to compare.
7. Reload: run type, advanced sections, table columns/filters/sort and result mode persist.
8. Check strategy refresh feedback and Journal cards/table persistence.
9. At approximately 1024px, tables scroll internally without horizontal page overflow.

No live broker order routes, strategy tuning, provider-routing changes or new
portfolio model were introduced. Continuous/TradingView parity remains unverified
without real reference exports; current-stock-universe survivorship limitations remain.

Backtest is the normal workflow. Optional research sections preserve chronological
60 / 20 / 20 boundaries, editable periods and descriptive sensitivity. Settings
defaults apply to new forms; Use settings retains saved configuration. Cross-feature
actions prepopulate symbol, dates and compatible timeframe without submitting.


## Run configuration and viewer

The required name defaults to `Run N` using the highest saved run ID plus one;
tags and notes are optional. Execution/cost/account/schedule controls live under
Advanced. Opening a saved run enters the dedicated Summary, Trades and Analysis
viewer, with Use settings and Back to Runs. Broker connection controls live in
Settings; Portfolio refreshes local snapshots without polling providers directly.

Queue/compute polling shares one in-flight request and stops when idle. An open
research viewer polls compact status/cell metrics; full snapshots load when opened.
Manual refresh/focus finds work submitted by another client. Old running backends
fall back to full experiment reads until their next normal restart.


Current background work, integrated parameter sweeps and progressive saved results
are described in [Backtest usability and Trade Review](BACKTEST_REVIEW_USABILITY.md).
The former page-local Jobs panel now lives in global Activity.
