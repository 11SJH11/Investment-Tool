# Backtest workflow — Checkpoint 9

## Choose a run type

The primary tabs are **Backtest, Runs, Strategies, Workspace**. Indicators remain
available from Strategies. The standalone Replay workspace is unchanged.

Select a strategy, symbols, requested dates, primary timeframe, balance, sizing,
name and research role. Review **Ready to run** before submitting. Auto session
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

### Validation suite

Choose non-overlapping development, validation and out-of-sample dates, an
experiment name and notes. All periods use the same base strategy/configuration.
Each symbol has its own experiment group. Submission immediately queues the jobs;
the form stays available. The live summary shows the first submitted symbol;
all completed symbols/periods remain accessible in Runs and batch comparison.
Opening a saved experiment reads immutable snapshots, without rerunning it.

### Sensitivity test

Choose one numeric parameter and up to nine values, using the displayed base
configuration and requested period. The role is development. Values outside the
declared parameter range are excluded. Existing research-only parameters remain
available; a frozen strategy may reject an unsupported override. The whole sweep
is saved; no winning parameter is selected automatically and no source defaults
are changed. Results and the descriptive sensitivity summary update as jobs finish.

## Queue and concurrency

- States: queued → preparing data → running → completed; failure/cancellation are
  terminal alternatives. Completed jobs link to immutable BacktestRunRepository runs.
- `MAX_CONCURRENT_BACKTESTS=2` by default; configuration accepts 1–8 workers.
  Configure another run while earlier jobs execute. Workers are in-process threads,
  not separate services; Python CPU throughput is subject to the GIL.
- Data preparation occupies a worker. Preparation has no invented percentage.
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

## Strategy Workspace

Follow the visible nine-step guide: create/copy, write Python, check syntax/save,
validate interface, add deterministic tests, run tests, configure, backtest, inspect
saved metrics/Trade Audit. New strategy loads the existing working template; the
plugin guidance explains StrategySpec, on_bar(ctx), EntrySignal and engine ownership.
The explicit trusted-code consent, built-in protection, subprocess timeouts and
redaction remain unchanged. Local Python is not a secure sandbox.

## Acceptance walkthrough

1. Choose VWAP, AAPL, a period with data, and review sizing/costs. Run it.
2. While it executes, change the name and queue another; the form stays editable.
3. Paste AAPL/MSFT/NVDA. Queue three independent runs; at most two jobs prepare/run.
4. Cancel a queued item, open a completion, and compare completed snapshots.
5. Switch to Validation and Sensitivity; verify only the relevant experiment controls.
6. Filter Runs by symbol/role, numeric boundaries and dates. Select two to compare.
7. Reload: run type, advanced sections, table columns/filters/sort and result mode persist.
8. Check Workspace guidance and Journal cards/table persistence.
9. At approximately 1024px, tables scroll internally without horizontal page overflow.

No live broker order routes, strategy tuning, provider-routing changes or new
portfolio model were introduced. Continuous/TradingView parity remains unverified
without real reference exports; current-stock-universe survivorship limitations remain.
