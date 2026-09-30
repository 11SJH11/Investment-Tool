# Background market history

Use **Settings > Data cache** to select a history window and choose **Update
missing favourite data** or **Update missing NQ1! data**. The default is 30 days;
longer windows, including two years, require an explicit action. Loading Ledger
or changing the watchlist no longer silently starts a download, even if an old
`keepFavouritesUpdated` preference is still present.

Jobs are backend-owned and continue after navigating away. Settings lists durable
jobs with symbols, requested bounds, covered request ranges, current chunk,
completed chunks, and provider/error state. All displayed coverage timestamps are
UTC. Coverage records successful requested ranges, including closed sessions;
it is not proof that every possible bar exists. Chunk row counts can include
shared endpoints and are not unique-bar totals.

**Pause** stops before the next provider acquisition/chunk. A current request must
finish safely. **Resume** continues a paused or failed job using persisted coverage.
After restarting Ledger, interrupted jobs are deliberately paused, not silently
restarted; use Resume. Provider 429 errors show a retry time and prevent resuming
before the reported cooldown expires. Authentication/entitlement, provider and
storage failures have sanitized messages; raw exceptions are not persisted.

## How coordination works

- Warming requests at most seven calendar days per chunk and persists each
  successful chunk through the existing canonical market-data service.
- New history starts near the requested end. Extensions attach to existing
  coverage and work backwards/forwards in bounded steps. If an existing interval
  is far away, the intervening gap is also covered in bounded steps; the cache
  retains its existing contiguous-coverage model.
- Charts, Replay and explicit backtest data requests use foreground priority.
  Waiting foreground requests acquire a provider before the next background
  chunk. Reentrant continuous-to-dated-contract calls retain their existing
  serialization and single-flight behavior.
- A running HTTP request, provider pagination, retry/cooldown or atomic file write
  is not preempted. Priority is between acquisitions, not a strict latency SLA.
  Sustained interactive work may delay warming. Providers can still be slow or
  unavailable. Reference/roll evidence can require additional historical sessions.
- Covered payloads are reused unless explicit refresh or corruption recovery is
  requested. Job progress is committed after canonical bars/coverage. A crash in
  between reuses the successful cache commit on resume.

## NQ1! safety

The existing dated-contract Parquet files, reference cache, causal roll schedule,
source-contract provenance and derived continuous snapshots remain authoritative.
Warming uses execution-safe raw data first and also constructs the chart cache
when backward-adjusted charts are configured. No OHLCV values, strategy rules,
margin rules, fills, sizing or saved research results are changed.

Automated mocked-provider tests cover raw and adjusted NQ cache reuse after
restart, including identical source contracts/prices with zero new provider calls
for covered history. This is not a new live Massive entitlement or latency claim.

## Persistence and operation

`market_warmup_jobs` is an additive SQLite table containing only job-control JSON
and update timestamps. It does not replace any market cache or alter existing
Journal/research tables. Old pre-Stage-4 in-memory job status cannot be recovered,
but any history it already cached is reused by a new update job.

Source changes do not update an already-running backend process. Restart Ledger
normally **after active research has finished** to load this implementation. No
restart or live data migration was performed during development.

## Verification

- `backend/tests/test_market_warmup.py`: chunk bounds, adjacent missing coverage,
  pause/resume/restart, checkpoint crash window, duplicate starts, API controls,
  sanitized cooldown failures, priority, cancellation while waiting and NQ reuse.
- Existing full backend fixtures retain engine/strategy/research output parity.
- `frontend/tests/market-warmup.test.js`: defaults, explicit requests, controls,
  cooldown and UTC coverage formatting.
- `frontend/tests/browser/market-warmup.mjs`: isolated mocked-API smoke for no hidden
  auto-download, explicit update, requested/covered/current ranges, Pause/Resume,
  navigation persistence and cooldown at 1024/1440/1920 pixels.
- [Verification commands](VERIFICATION.md).
