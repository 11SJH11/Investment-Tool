# Reliability and broker import implementation status

## Safety checkpoint

- Source checkpoint: `4dc3da4`, branch `checkpoint/pre-reliability-2026-09-29`.
- Runtime logs/bytecode were already dirty and were not added to the checkpoint.
- Do not read/edit `.env`, touch live `data/`, restart the running research service,
  or change strategy rules, engine semantics, fills, sizing, or market-data values.
- Tests use temporary storage. Test settings disable dotenv parsing entirely.

## Stages

| Stage | Scope | Status |
|---|---|---|
| 1 | Separate research notes/items and experiments | Complete: 18 focused tests pass |
| 2 | Restore green verification gate | Complete: 611 backend / 78 frontend; build and browser pass |
| 3 | Crash-safe raw market cache | Complete: 627 backend / 78 frontend; production build passes |
| 4 | Bounded, resumable, interactive-priority warming | Complete: 642 backend / 80 frontend; build and browser pass |
| 5 | Global simulation budget and 5x5 parity benchmark | Complete: 647 backend / 80 frontend; build/browser and exact benchmark parity pass |
| 6 | Compact research polling | Complete: 649 backend / 84 frontend; build and browser pass |
| 7 | Replay leave/checkpoint guard | Complete: 649 backend / 88 frontend; build and browser pass |
| 8 | Safe actionable error categories | Complete: 737 backend / 88 frontend; build and browser pass |
| 9–10 | Protected scope and final acceptance | Pending final verification |
| 11 | Documentation/test classification and cleanup | Pending |
| 12 | TradeLocker read-only import | Pending official API review |
| 13 | MetaTrader 5 read-only import | Pending official integration review |
| 14 | Canonical broker execution model | Pending |
| 15 | Broker frontend | Pending |
| 16 | Safe root `.env.example` | Pending |
| 17 | Untrack generated files, retain local copies | Pending |
| 18 | Broker fixture acceptance | Pending |

## Stage 1

Restored the original notes/items repository behaviour from source history as
`ResearchItemRepository`. Experiment persistence is now explicitly named
`ResearchExperimentRepository`. Existing tables and IDs are unchanged.
The old experiment import remains a compatibility alias for existing callers and
workers; it is not a combined repository. Tests exercise real container wiring,
API list/upsert/delete, source identity, distinct manual notes, restart preservation,
and coexistence with experiment documents.

Validation: `test_research_items_api.py`, `test_phase63_journal_research.py`,
`test_parent_research.py`: **18 passed**.

## Failure classification

- Missing research-item methods: **production regression**; restore production
  implementation and preserve the existing upsert test.
- 18 research-axis failures: **valid behaviour, stale test contract**; update the
  signature without removing numeric validation assertions.
- Continuous warm-cache physical-read assertion: **valid behaviour, stale contract**.
  Durable reuse promises identical data/provenance and zero provider requests while
  reference evidence remains valid. First disk reads after cold preparation/restart
  are allowed; subsequent in-memory hits are separately asserted.
- Browser research wording/view placement: **valid behaviour, stale test contract**.
  Follow current dedicated Research Viewer navigation.
- Removed heatmap corner-selection UI assertions: **obsolete UI workflow**; exact
  experiment generation, heatmaps, cell opening, and low-sample checks remain required.

No tests or documents have been deleted at this checkpoint.

## Stage 2 ? completed 30 September 2026

- Updated all stale `axis_values` calls to the four-argument public contract;
  retained rejection, sentinel, decimal, integer and lattice assertions.
- Documented durable NQ warm-cache reuse: identical bars/provenance, zero additional
  provider requests while reference evidence is valid. Separately verifies first
  disk read, memory hit, new-service reuse and caller-mutation isolation.
- Browser smoke follows the dedicated Research Viewer, returning to Backtest to
  define another experiment. Removed obsolete corner-selection UI assertions;
  retained spectrum/grid, failure visibility, low N, default control and exact
  run opening, and added interaction-residual view navigation.
- `Verify-Ledger.ps1` runs all backend/frontend tests plus an isolated production
  build. `frontend/verify-build.mjs` disables dotenv loading. No live process restart,
  live data writes, credential reads or installed dependency changes are required.
- Corrected one encoding-only worker-label change introduced during the repository
  rename; no execution behaviour changed.

Final verification on this tree:

- Backend: **611 passed**, one existing Starlette TestClient deprecation warning,
  73.99 seconds. Audit baseline was 589 passed / 20 failed; two API/container
  regression tests were added in Stage 1.
- Frontend utility tests: **78 passed**, zero failures.
- Production build: **118 modules**, success; existing 823.81 kB JS chunk warning.
- Isolated mocked research browser smoke: passed at **1024 / 1440 / 1920 px**, no
  page overflow or runtime exceptions.
- `git diff --check`: passed for changed source/docs.
- Frozen strategies, engine and indicators: source unchanged from `4dc3da4`.

Environment caveat: sandbox restrictions denied some Node source reads and caused
spurious unresolved imports. Frontend tests passed outside those restrictions;
the isolated build helper passed when invoked directly outside them. Do not
modify application imports to work around this execution-environment limitation.

Next stage after Stage 2: crash-safe raw Parquet writes (see Stage 3 below).


## Stage 3 - crash-safe market cache

Raw appends and derived replacements now write to a unique temporary file in the
same directory, decode every column with a streaming validation aggregate, check
schema/row count, flush the file, then atomically replace the destination. Coverage
is updated only after the payload is published. No database migration is required.

A process interruption before replacement leaves the previous payload intact.
An interruption between replacement and the SQLite coverage commit leaves valid
bars with conservative coverage; an overlapping retry merges/deduplicates safely.
These are two storage resources, not a cross-resource transaction.

Missing/corrupt covered payloads are repaired from the provider for the complete
claimed interval plus the request. Provider/write failure preserves the existing
file and coverage evidence. Corrupt derived continuous snapshots rebuild from
cached dated contracts without provider calls when those sources remain valid.
NQ source-contract provenance is preserved.

Successful empty responses now have durable empty payloads when no cache exists.
An empty append to an existing payload does not rewrite it or coerce its dtypes.
This is essential to preserve research input fingerprints and resumability.
Existing raw frame-cache identities remain scoped to file mtime/size; unrelated
prepared inputs are not globally evicted on every append.

New tests in `backend/tests/test_market_cache_recovery.py` cover interruption at
validation/flush/replacement, invalid temporary content, first-write failure,
post-replacement coverage failure, missing/corrupt repair, failed repair, restart,
empty responses/appends, uncommitted payloads, access errors, orphan temporaries,
and continuous-futures reconstruction. The in-memory store fixture now implements
`has_bars`; its existing coverage and concurrent single-flight assertions remain.
No tests were removed and no strategy/results assertions were relaxed.

Limitations: provider recovery still requires actual provider availability. An
ungraceful process kill can leave an ignored `.tmp` file; it is never treated as
bars, and cleanup does not delete another writer's temporary file. This change
protects process-interruption publication; it is not a guarantee against storage
hardware failure or a filesystem that does not support atomic replacement.
Existing in-process provider coordination remains; a new multi-process cache
writer locking protocol is outside this stage.

Stages 4 and 5 are not started. Stage 4 remains bounded, resumable warming with
interactive request priority; Stage 5 remains the global CPU budget and measured
5-by-5 before/after parity benchmark. The live service was not restarted, live data
and credentials were not read/edited, and generated logs/bytecode were not staged.


Stage 3 final verification (30 September 2026):

- `powershell -ExecutionPolicy Bypass -File ./Verify-Ledger.ps1 -OutputDirectory C:/Users/jamie/Project/reliability-stage3-final`: passed.
- Full backend: **627 passed**, one existing Starlette deprecation warning, 78.40s.
  Includes **16 new cache recovery cases** plus all existing research, Replay,
  futures, broker, Journal, strategy and engine regressions.
- Full frontend utility suite: **78 passed**, zero failures.
- Production build: **120 modules**, success, 1.38s; existing large-chunk warning
  (827.96 kB JS / 245.97 kB gzip). Artifacts are outside the repository.
- Focused cache/futures run: **42 passed**; focused cache/queue/research run:
  **75 passed** before the final two empty-payload cases (both pass in full suite).
- `git diff --check`: passed for staged Stage 3 files.
- Protected strategy, engine and indicator Python sources match checkpoint
  `4dc3da4` after newline normalization.
- No new browser smoke was required for this storage-only change; no frontend
  source was changed. Stage 2 browser results are recorded separately above.

The initial verification failures were corrected, not deleted: the memory-store
fixture needed the cache-presence interface, and production empty-appends needed
to preserve payload dtypes/fingerprints and unrelated warm-cache entries. Final
verification was rerun on the corrected tree. At the Stage 3 boundary, Stages 4-18 remained pending (Stage 4 is now complete below).


## Stage 4 - completed 30 September 2026

- Replaced symbol-sized warm requests with seven-day adjacent chunks. Existing
  canonical provider coverage guides planning so an old requested range cannot
  cause one huge bridge download. Each successful chunk survives restart.
- Added reentrant provider coordination that lets waiting foreground Charts,
  Replay and explicit backtest requests precede the next background acquisition.
- Added durable `market_warmup_jobs` job-control documents, listing, Pause/Resume,
  interrupted-job recovery to paused state, sanitized provider categories and
  Retry-After cooldown enforcement. This is an additive table, with no changes to
  existing data/strategy/run schemas or the canonical Parquet store.
- Removed silent startup/watchlist/six-hour two-year downloads. Default explicit
  history window is 30 days. Settings owns a focused download panel with requested
  and covered ranges, current chunk, progress and controls. Navigating away does
  not stop the backend job.
- Preserved NQ dated contracts, references, roll provenance, raw execution and
  optional adjusted chart snapshots. Existing source values/rules remain unchanged.
- Added the permanent [warming guide](MARKET_CACHE_WARMING.md) and README link.

Verification on current source:

- Full backend: **642 passed**, one existing Starlette deprecation warning,
  **72.88s** (previous stage: 627; **15 new Stage 4 tests**).
- Full frontend utility tests: **80 passed**, zero failures (previously 78).
- Production build: **120 modules**, success, 825.24 kB JS / 245.55 kB gzip,
  61.17 kB CSS / 12.23 kB gzip; existing large-chunk warning only.
- `Verify-Ledger.ps1` passed with external artifacts under
  `C:/Users/jamie/Project/reliability-stage4-verify1`; final browser build also passed
  under `C:/Users/jamie/Project/reliability-stage4-browser/frontend`.
- Focused backend runs: **43 passed** (warming/cache/queue/futures) and **41 passed**
  (expanded warming/API/continuous-futures tests).
- Isolated browser smoke passed at **1024 / 1440 / 1920 px**, with no page overflow
  or runtime errors. It checks legacy auto-warm preference does not trigger POST,
  explicit NQ download, ranges/chunk progress, pause/resume, Settings -> Overview ->
  Settings persistence and provider cooldown. Initial incomplete Broker/Workspace
  mocks were corrected; production was not changed to accommodate the mocks.
- Protected strategy/engine/indicator sources match checkpoint `4dc3da4` after
  newline normalization. Full deterministic research/engine fixtures pass.
- `git diff --check` passed for Stage 4 source/docs/tests.

Limits: in-flight provider calls/cooldowns are not preempted; foreground priority
applies between acquisitions. Live Massive was not called; credentials were not
read. The running Ledger service was not restarted and live data was not touched.
The new code takes effect on the next normal restart after active research ends.
Only isolated test/build/browser processes were launched. Existing generated
logs/bytecode changes remain unstaged.

**Stage 5 is next and has not been started.** No global CPU budget fix or new
5-by-5 performance benchmark is claimed. Stages 5-18 remain pending.

## Stage 5 - completed 30 September 2026

One application-owned CPU reservation budget now covers ordinary queued runs,
direct service/API simulations, validation runs, spectra and interaction parent
pools. Input preparation and parent coordination remain separate. Reservations
release on success, failure and cancellation; nested service calls do not double
count. Worker pools cannot independently multiply the configured global limit.
Settings and queue show configured/resolved budget, reserved slots and queued
simulations. Lowering the target drains current work; it does not kill simulations.

Research pools conservatively retain their lease through their final batch and
pool shutdown. Idle capacity within a leased pool is not dynamically loaned. This
is one application process, not distributed admission across multiple servers.

Verification: **647 backend passed**, one existing warning, **72.17s**; **80 frontend
passed**; production build passed (120 modules; existing large-chunk warning).
**27 focused queue/research/budget tests passed**. Isolated research browser smoke
passed budget display, spectrum/interaction, partial failures, exact run opening,
and 1024/1440/1920 overflow/runtime checks. `git diff --check` passed.

Existing five-session, 1,950-bar, 5x5 ORB benchmark: **82.867s before**, **80.363s
after**, actual four workers in each; zero provider calls. **25/25 exact cell
hashes match** for trades, metrics, setups, analysis and equity curves. See
[recorded benchmark](GLOBAL_BUDGET_BENCHMARK.json). One timing sample under concurrent
user research is not a statistically established speedup. Engine/strategy rules
were not edited; only service admission around the existing engine call changed.

No live process restart, live data access or credential read occurred. Stage 6 is
next; Stages 6-18 remain pending at this commit.

## Stage 6 - completed 2 October 2026

Queue and research-history requests now opt into compact SQL projections. An open
research viewer loads its definition once, then polls cell status and aggregate
metrics without transferring full run trades, equity curves or configurations.
The original full endpoints and persisted run/experiment snapshots remain intact;
there is no schema migration. MFE/MAE and stop/target summaries retain existing
missing-value and sample-count semantics.

Queue and compute controls share one in-flight request and timer. Polling stops
when idle/terminal and when the last subscriber unmounts. Manual refresh, focus,
and submissions refresh status; newly queued work in another client is discovered
on focus/refresh rather than through perpetual idle polling.

Verification: **649 backend passed** (83.23s, existing Starlette warning),
**84 frontend passed**, production build passed (122 modules; existing large-chunk
warning). Focused queue/research/status tests: **24 passed**. Four new frontend
polling tests cover request coalescing, terminal/unmount stopping, error recovery
and compact metric equivalence. Isolated mocked browser research smoke passed at
**1024/1440/1920**, including compact request routing, spectrum, interaction,
partial failure and exact run opening. No overflow/runtime errors. Source diff
whitespace checks passed. Artifacts: `C:/Users/jamie/Project/stage6-verified`.

Limitation: SQLite still scans saved JSON to compute the small diagnostic summary;
this reduces Python decoding and response size, not all database CPU work. Live
research was not restarted, live data/credentials were not accessed, and unrelated
user strategy edits remain untouched. Stage 7 and later remain pending.

## Stage 7 - completed 2 October 2026

Replay navigation now offers Stay, Save checkpoint and leave, or Leave/discard
when a session has changes, an active position or a pending order. Replacement
loads, restart and resume also use this guard. Playback pauses and shortcuts are
suppressed while the modal is open. Browser reload/close uses the browser's native
unsaved-state warning (browsers do not permit custom save controls there).

Checkpoint writes verify browser-storage readback before allowing navigation.
Quota/access failures leave the session open with an actionable message. In-flight
Replay steps must settle before saving/leaving. Existing canonical visible/frontier
timestamps, integrity state, positions and pending orders are retained; checkpoints
now also retain contracts, the closed trade and its Journal status. Failed data
loads no longer claim successful resume or clear the existing Journal status.
Replay fills, sizing, causality, provider paths and broker identities are unchanged.

A final compatibility check added a Stage 6 fallback for the old backend that may
still be running research: a missing status endpoint falls back to the original
full experiment endpoint. Real non-404 failures remain errors. Compute settings
load once through the original endpoint if queue responses lack compute fields.
No backend restart is needed merely to keep the frontend usable.

Verification:

- Full backend: **649 passed**, one existing Starlette warning, **85.03s**.
- Final frontend suite: **88 passed** (three checkpoint tests and one legacy-server
  compatibility test added after Stage 6).
- Final production build: **124 modules**, success; 830.15 kB JS / 247.26 kB gzip;
  existing large-chunk warning. Final artifact: `stage7-browser/frontend` outside
  the repository. The full verification helper also passed in `stage7-verified`.
- Isolated mocked browser: pending order, active position and closed trade survive
  save/leave/resume; Stay and discard work; simulated quota failure cannot leave;
  failed resume cannot claim success; beforeunload warning and blocked shortcuts
  pass. Dialog/page overflow checks pass at **1024/1440/1920** with no runtime errors.
- Research browser regression passed against both compact and legacy API fixtures
  at all three widths. A missing Workspace fixture field and request-recording
  order were corrected in the new browser mock, not in production.
- Source whitespace checks pass. No tests/documents deleted or coverage relaxed.

Limits: this is one browser-local checkpoint, not durable server-side Replay
sessions or automatic crash recovery. Clearing browser storage removes it. Resume
still needs the corresponding historical bars. Checkpoint saving is not Journal
submission. Discard abandons current changes but retains the previous checkpoint.
No live data/credentials were read, no running Ledger process was restarted, and
user strategy edits/generated files remain outside these commits.

Next: Stage 8 safe actionable errors. Stages 8-18 are not complete; TradeLocker,
MT5, canonical broker imports and repository cleanup remain pending.

## Stage 8A - safe queue, worker and cache-warming errors

Shared allowlisted messages distinguish authentication/configuration, HTTP 403
permissions/entitlement, rate limiting with a UTC retry time, missing history,
invalid parameters, strategy execution, storage/cache failure and worker termination.
Unknown exceptions stay explicitly unclassified; exception text, provider bodies,
URLs and account/token strings are never copied into these messages.

Queue errors keep their existing string field with a category prefix. Research
cells and parent failures reuse the classifier. Cache warming retains structured
category/retry fields and its existing cooldown enforcement. Massive's known
missing-history/configuration failures use typed exceptions; original ValueError
versus RuntimeError catch contracts are preserved. No schema or saved-result
migration, automatic retry, strategy/fill/accounting change or live restart.

New deterministic tests cover all categories, malicious exception text, invalid
retry delays, exact retry timestamps, strategy ValueError context, and persisted
queue/compact-list messages. Initial focused suite: 91 passed; final classifier
suite: 22 passed. Full verification: **671 backend passed** (85.81s), **88 frontend passed**,
production build and source whitespace checks passed. Existing Starlette and large
JS chunk warnings only. Isolated artifacts: `stage8a-final` outside the repository.

Remaining Stage 8: sanitise synchronous Charts/Replay/backtest API failures and
verify the resulting response contracts. Do not interpret Stage 8A as application-
wide secret-sanitisation coverage or as a completed Stage 8.

## Stage 8B - synchronous data/research API errors

Charts (including batched indicators), raw market bars, Replay bars/indicators,
Trade Audit and direct backtests now return structured safe details with category,
message and optional UTC retry time. HTTP 429 also carries a numeric Retry-After
header. Existing non-rate-limit HTTP status codes remain unchanged, and the
frontend already supports detail.message. The queue's legacy error-string contract
and saved result schemas remain unchanged.

Missing provider configuration and Replay history use typed exceptions preserving
existing ValueError/RuntimeError contracts. Cache corruption is classified as
storage. Research profile partial-success responses no longer embed raw SEC
exceptions. Unexpected batched-indicator failures preserve bars and report a safe
per-indicator error rather than escaping as an unhandled exception.

Coverage: 64 parameterised API cases exercise eight entry points against auth,
permissions, rate-limit, missing provider/history, corrupt cache, invalid params
and unknown execution failures. Two additional tests cover partial Research and
indicator failures. No test uses live credentials or providers. Final verification: **737 backend passed** (92.35s; 88 new tests since Stage 7),
**88 frontend passed**, production build passed (124 modules), and source diff
whitespace checks passed. Existing Starlette/large-chunk warnings only. Final
isolated artifacts: `C:/Users/jamie/Project/stage8-final`.

Focused API/classifier/Replay/Research checks: **102 passed**, followed by **66 API
tests passed** after adding the final indicator case. Isolated browser checks
passed structured missing-history/rate-limit messages and the existing Replay
checkpoint/leave flows at 1024/1440/1920, without overflow/runtime errors. The
browser-tested frontend is byte-identical to the final build. No live providers,
credentials, databases or running Ledger processes were accessed/restarted.

Stage 8 is complete for this scope. Changes take effect at the next normal backend
restart after active research finishes. Stages 9-18 remain pending; no later stage
was started. User strategy edits and existing generated-file changes remain
outside these commits.

Boundaries: this is the requested research/data error handling, not a claim that
all application endpoints or third-party logs have undergone a security audit.
Internal queue/workspace validation messages and broker-specific handling retain
their existing contracts. Unknown exceptions remain unclassified rather than
being guessed from arbitrary exception text. A provider's HTTP 403 identifies
access denial, not proof of which subscription entitlement is missing. Existing
valid empty market sessions remain valid; this change does not invent missing
bars or redefine successful empty responses. No live Massive acceptance was run.
