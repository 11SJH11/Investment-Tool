# Exact spectrum and interaction research

Ledger runs each parameter value/cell through the same event-driven BacktestEngine
as a standalone run. Results are never synthesized by filtering another run’s
trades. Strategy source, defaults, completed-bar visibility, callback order, fills,
costs, same-bar policy and excursion definitions are unchanged.

## Workflow

Configure one symbol, strategy, dates, session and account in Backtest. Open
**Sensitivity / spectrum & interaction grid**. Choose numeric axes, explicit
values or Start/End with Step or Number of values. Preview the exact values before
submission. Invalid/duplicate values are rejected, not dropped or rounded silently.
Decimal arithmetic validates type, bounds and declared step. A declared default
sentinel is accepted when valid for that parameter. Count spacing must also align
with the parameter’s declared step; choose another count if it does not.

Limits are 25 values for spectra and 8 values per axis / 64 cells for interaction
grids. Start coarse: 3×3 or 5×5. The user supplies an experiment name, notes, tags
and data role (`development`, `validation`, `out_of_sample`). Experiment type
(`spectrum`, `interaction`) is separate from role. “Parity” refers only to
deterministic equivalence tests, not an experiment type.

Submission creates **one queue item**. It progresses through queued, preparing
shared data, running N/total simulations, analysing results, saving, completed.
Failures remain visible per cell; successful cells are retained. Cancel affects
the parent and its remaining cells. Retry resumes incomplete cells, provided the
prepared input fingerprint has not changed. If data changed, create a new
experiment rather than mixing old and new source snapshots.

Open the experiment from the queue or Runs → research. Each point/cell opens its
exact immutable saved run. Child runs are excluded from the ordinary Runs query;
they remain accessible by ID and experiment. Removing queue history does not
remove experiment documents or saved results. Restart marks interrupted parents
failed for explicit retry; a single saved child cannot mark a parent completed.
Recovery reconciles saved child IDs before rerunning any missing cell.

Charts show actual completed results; losing cells and incomplete cells are not
hidden. Tooltips include parameter values, N, average R, PF, total R, drawdown and
win rate. N < 30 is labelled low sample. Recorded MFE/MAE averages retain their own
observation counts. Missing metrics remain unavailable. Colour is centred on zero
with a minimum scale so tiny differences are not exaggerated. Stop/target
percentages count realised exit-reason categories. There is no ranking, automatic
region selection, default mutation or “winner”.

For a finer follow-up, return to Backtest, retain the intended base configuration,
and enter a narrower explicit/range axis definition. Preview every new experiment
before queuing it. The dedicated Research Viewer does not offer corner-selection
or automatically create a follow-up grid.

Existing recorded-feature buckets remain descriptive hypothesis-generation tools,
**not exact counterfactual backtests**. A new two-dimensional descriptive explorer
is deferred; the authoritative interaction grid runs real simulations.

## Preparation and CPU execution

`BacktestService.prepare` performs the same validation, provider resolution,
timeframe/session preparation and optional diagnostic warm-up as standalone runs.
Each parent calls it once. Every cell constructs fresh strategy, account, position,
pending-order, guardrail, cooldown and mutable indicator state. Frames exposed to
simulations are copied; a strategy or caller cannot contaminate the shared inputs.

The parent owns provider access, progress and SQLite writes. A bounded spawn-based
process pool handles independent CPU simulations. Auto conservatively requests two
workers, constrained by CPU and available memory; explicit 1/2/4/6/8 selections
are resource-capped. Two logical cores and roughly half available memory are
reserved where possible. Workspace strategies use one parent-process worker to
avoid changing their activation/import contract.

One application-owned reservation budget now bounds ordinary queued runs, direct
API simulations and all research parent pools together. Preparation/coordinator
threads do not reserve CPU capacity; research parents reserve up to the currently
available budget after preparing their input snapshot. Pools retain that lease
until shutdown (including cancellation). They cannot each multiply the global
limit. A single causal simulation remains sequential. Settings and the queue show
the resolved budget, reserved worker slots and queued simulations.

Reservations are conservative capacity bounds, not sampled CPU utilization. A
research pool retains its reservation through its final batch and persistence;
idle slots within that pool are not dynamically loaned to another parent. Lowering
the limit lets existing reservations drain without killing in-flight simulations;
new work waits until capacity is available. This is one running Ledger application
process, not a cross-process/distributed scheduler. Resource caps still apply.

A private temporary prepared-input file is written once and read once per worker
initializer. Frames are not reserialized for every cell. Workers receive no
provider, database or repository objects. They return results to the parent for
persistence. This is a transient batch input, not another persistent OHLCV cache.
The file is removed when the pool exits. A shared cancellation event is checked at
the engine’s existing progress boundaries; queued futures are cancelled, running
workers exit cooperatively. Cancellation does not erase completed immutable runs.

Memory mapping/shared-memory arrays were not adopted: one read per worker is a
simple bounded starting point, and the measured frame sizes do not justify a new
serialization/ownership contract yet. Worker and parent peak RSS, CPU seconds,
per-cell stages, preparation and persistence timings are retained in the parent
document. Sum of worker peak RSS is an upper bound, not simultaneous sampled RSS.
Nested stage timings are inclusive and must not be added blindly.

## Existing and new caches

Existing persistent caches remain authoritative: namespaced raw OHLCV Parquet,
SQLite coverage, Massive contract references and versioned roll evidence. Provider
locks/single-flight coverage checks are retained. No result cache is introduced.

The process-local frame cache has LRU eviction, TTL, defensive copies and entry /
approximate-memory limits. Defaults: 32 entries, 256 MiB, 120 seconds. Override with
`LEDGER_FRAME_CACHE_ENTRIES`, `LEDGER_FRAME_CACHE_MB`, `LEDGER_FRAME_CACHE_TTL`.
Zero entries disables it. Memory figures include DataFrame deep memory estimates,
not all Python allocator overhead. Cache diagnostics record hits/misses and
physical Parquet reads, without network probes solely for diagnostics.

* Raw frames: resolved namespaced file path, file size and nanosecond mtime plus
  requested range. A covered superset can safely supply a subset.
* Prepared chart/session frames: full scalar content fingerprint including column
  order/dtypes and provenance, timeframe, session, session profile, preparation
  version. Aggregated subsets are deliberately re-prepared: their boundary buckets
  can differ. Underlying raw subsets still reuse the range cache.
* Continuous frames: provider namespace/base endpoint, root, resolution, exact
  range, contract definitions, current roll evidence and dated-file fingerprints.
  Reference and roll evidence are checked **before** reuse. Changed evidence or
  source files invalidate identity. Direct providers without durable source
  fingerprints do not use the derived cache. Adjusted and raw namespaces differ.

Force refresh clears process-local entries and refreshes durable data/schedule
under the existing provider lock. Source changes outside Ledger are detected by
file size/mtime; external tools must not deliberately preserve both while changing
content. Content fingerprints independently protect prepared frames.

Continuous superset slicing is deliberately limited to dated/raw input reuse;
adjusted-series anchoring and range-dependent roll sets make blind derived slicing
unsafe. Calendar-front fallback still uses its existing reconstruction path.

## Measured hot path and causality

Profiling identified repeated completion filtering/timestamp conversion in
`StrategyContext.bars`. The engine now builds completion indexes once per
simulation and binary-searches completed prefixes. Nonmonotonic or missing
completion times fall back to the original filter. Count, index labels, copies,
naive/UTC normalization and `available_at` semantics are tested against the
original path. No future bars are exposed and no indicators are shared mutably.

Session validation inside the unchanged ORB/VWAP strategy helpers remains a CPU
hotspot. Strategy-specific ATR/volume precomputation and vectorized strategy logic
were deliberately not changed in this infrastructure task.

GPU acceleration is not enabled. The authoritative simulator has sequential,
path-dependent state and branch ordering; a GPU rewrite would need a separate
parity and benchmark project. Monte Carlo, ML or large matrix feature analysis may
be more suitable later. CPU-only deterministic execution remains first-class.

## Futures preflight and limitations

The expandable futures preflight loads raw execution data, reports alias, provider,
requested/available period, schedule versions, source contracts, tick/point values,
strategy/session and full-notional capacity at the first available open. ORB still
uses the New York 09:30–16:00 cash window. It rejects invalid provenance and reports
provider/data failures without exposing arbitrary provider exceptions.

This is not a simulated sizing guarantee: risk-based sizing still depends on the
signal stop and subsequent equity; costs/gaps may also change actual entry. No CME,
broker or prop-firm margin is invented. NQ is 0.25 tick / $5 tick / $20 point; MNQ
is $2 per point. Continuous execution uses raw dated prices and existing roll
protections; no cross-contract position transfer is added.

Real provider latency, entitlements, throttling and exchange/reference data quality
remain external constraints. Fixture benchmarks do not establish live Massive
performance or TradingView parity. See [recorded global-budget benchmark](GLOBAL_BUDGET_BENCHMARK.json)
and the measurement caveats below.

## Verification / operations

Use isolated data directories and never a user database for tests. Backend:
`python -m pytest -q -p no:cacheprovider`; frontend: `node --test tests/*.test.js`
and `npm run build`. Focused suites: `test_research_infrastructure.py`,
`test_research_futures.py`, `test_parent_research.py`, `test_continuous_execution.py`.
The browser fixture `frontend/tests/browser/research-experiments.mjs` intercepts
all API traffic and checks production UI behaviour at 1024/1440/1920px.

Benchmark scripts use synthetic, explicitly labelled OHLCV and temporary SQLite /
Parquet directories: `benchmark_research.py`, `benchmark_futures_research.py`,
`benchmark_parent_research.py`. Preserve a source-only pre-change app directory for
`--app-root` comparisons; never copy credentials or production databases.


## Global-budget verification (30 September 2026)

The existing 5x5 ORB fixture (five sessions, 1,950 minute bars) ran before and after
with a global budget of four and a research request of four. Wall time was 82.867s
before and 80.363s after. Both runs completed all 25 cells with zero provider calls;
all 25 SHA-256 digests of trades/metrics/setups/analysis/equity curves match exactly.
This is one measurement while existing research remained running, not evidence of
a statistically established speedup. [Recorded benchmark](GLOBAL_BUDGET_BENCHMARK.json).

Reproduce with `backend/.venv/Scripts/python.exe -B backend/tools/benchmark_parent_research.py
--workers 4 --global-workers 4 --output <external-output.json>` from the repository
root. The script uses temporary data, disables dotenv parsing, and requires no live
provider credentials. The simulation budget changes no strategy/engine rules.
