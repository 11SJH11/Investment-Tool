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
| 4 | Bounded, resumable, interactive-priority warming | Pending |
| 5 | Global simulation budget and 5×5 parity benchmark | Pending |
| 6 | Compact research polling | Pending |
| 7 | Replay leave/checkpoint guard | Pending |
| 8 | Safe actionable error categories | Pending |
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
verification was rerun on the corrected tree. Stages 4-18 remain pending.
