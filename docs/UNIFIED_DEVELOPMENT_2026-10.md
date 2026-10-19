# Unified Ledger development — 19 October 2026

This is the current continuation handoff. The active brief prioritizes a unified
Windows-local application and explicitly authorized MT5 **demo** deployments.
Live-money execution is out of scope for this phase. No broker orders have been
authorized or sent by this integration.

## Checkpoint 1: integration

Primary directory: `C:/Users/jamie/Project/Investment-Tool`.
Integration branch: `integration/unified-ledger-20261019`.
Original master boundary: `f96d62a`. Feature boundary: `5337ec9`.
User Gold sources were preserved in `9688ec0` before merging.

Recovery branches:
- `recovery/pre-unify-master-20261019`
- `recovery/pre-unify-feature-20261019`

The feature branch and `Ledger-mt5-research` worktree remain available. No push,
worktree deletion, credential copy or database replacement was performed.
The original commit's VWAP strategies and research outputs are retained. The
previously untracked Gold T01–T06 module, comparison utility and instructions are
now tracked. Run 208–215 exports remain user-owned untracked files; 35 source/export
files were copied into local recovery storage and hash-verified after integration.

### Authoritative data and recovery

`Investment-Tool/backend/data/ledger.db` remains authoritative. At integration it
contained 213 saved runs, 11 Journal trades and 132 Portfolio broker records.
Run 209 is `gold_asia_15m_ifvg_research_v1`; Run 211 is
`gold_ifvg_v2_skip_23et`. All saved-run IDs, Journal fields and Portfolio IDs,
notes and tags matched the consistent backup. Provider `facts` subsequently
changed while the original app remained active; those newer facts were retained.

Recovery storage is **not disposable test output**:
`.ledger-integration-recovery/20261019/` contains:
- `ledger-consistent-snapshot.db`: completed SQLite online backup using a stable
  read transaction, including committed WAL contents.
- `data-inventory.json`, `data-locations.json`, `data-preservation-check.json`:
  counts, locations and preservation checks without credentials.
- `preserved-files.json` and `files/`: original source/export copies and SHA256s.
- `failed-merge-created/`: verified new files retained after an ACL-blocked first
  merge attempt. The subsequent merge succeeded without source conflicts.
- `ledger-before-integration.db`: **incomplete first backup**, retained for now;
  do not use this file for recovery. Consult the completed-backup manifest instead.

Original market cache: 30 files / 75,680,067 bytes at inventory time. Feature Gold
acceptance cache: 121 files / 5,091,943 bytes. Neither cache was replaced or merged.
The feature Gold acceptance database contains two generated real-data acceptance
runs and no Journal/Portfolio records. Its other acceptance database is empty.
These are test evidence, not unique user trading records; they remain in the
feature worktree rather than being imported with colliding IDs into the user DB.
Synthetic benchmark/browser databases also remain isolated there.

### Verification and narrow fixes

The integrated backend boots on localhost with an isolated test database and no
provider/model credentials. Its API exposes Gold V1 and all six variants. New
T01 acceptance tests preserve Sunday/DST behavior, +0.68R next-bar breakeven and
the 23:00 confirmation exclusion without changing any strategy source. All 22
Gold acceptance cases passed.

The first full backend run found a queue test that incorrectly assumed thread
slot acquisition follows submission order. The test now discovers actual active
and queued jobs before cancelling one of each. Concurrency, cancellation and saved
result assertions remain; production scheduling was not changed. All 19 focused
queue/Gold integration cases passed. Final full-suite results are recorded below.

All 138 frontend tests passed in a serial rerun. The first parallel invocation
hit transient Windows EPERM reads in two unchanged test files; both also passed
individually. Production build passed. Production-browser Gold, Portfolio, MT5
and export/selection checks passed at 1024, 1440 and 1920px without runtime errors
or page overflow. A fresh Vite session with dependency rebuilding also passed
Gold acceptance after an earlier development-server resolution failure for an
existing unchanged file. No application workaround was introduced for that failure.

### Test artifacts

New verification outputs are inside `.ledger-test-artifacts/` with backend,
frontend, browser, integration, logs and temporary subdirectories. Pytest's app
temporary directory and Python temporary-file default are repository-local;
Windows TEMP/TMP are not globally changed. The new directories are Git-ignored.
This begins the artifact-organization requirement; legacy-tool migration, failure
log retention and the parent-directory dry-run cleanup report remain outstanding.
No pre-existing parent folders have been deleted.

## Remaining checkpoints

2. Complete MT5 demo gateway and account-wide risk enforcement, broker protective
   orders, uncertain-submission reconciliation, mocked acceptance and terminal
   dry run. Existing sizing, snapshots and disabled intent storage are foundations,
   not an implemented submission gateway.
3. T01 frozen-source deployments, monitoring, background execution, durable candle
   frontiers, pause/stop semantics, Journal identity and explicit demo authorization.
   No deployment is currently permitted to submit orders. Historical Run 211 and
   forward demo performance must stay separate.
4. Genuine Gold Research Agent campaign, source/coverage validation, authorized
   model Critic/Manager and secure structural research. Do not weaken holdouts.
5. Live Backtest Preview, existing Replay and causal per-trade evidence improvements.
6. Measured performance, concurrent storage diagnostics, unified notifications and
   safe artifact cleanup. The existing `[storage]` failures are not yet diagnosed.
7. Later live-money/MQL5/distributed/hosting roadmap remains deferred behind demo.

Use the existing Windows launcher for ordinary local use. Do not use the isolated
`tools/run_isolated.py` launcher when expecting the original user database: it
intentionally chooses `.ledger-runtime/data`. Restart the ordinary app when ready
to load newly integrated code. Do not expose the development API publicly.

See [the prior detailed feature handoff](MT5_DISTRIBUTED_RESEARCH.md) for completed
MT5 history, Gold preparation, Portfolio, exports and broker-foundation evidence.

### Final integration verification

- Backend: **1,601 passed, 38 skipped, 1 warning**, 595.14 seconds. Skipped
  opt-in acceptance tests are not claimed as freshly verified Docker tests.
- Frontend: **138 passed** (`node --test --test-concurrency=1 tests/*.test.js`).
- Production build: passed (12.40 seconds); existing chunk-size advisory remains.
- Browser checks: Gold settings, current Portfolio holdings, MT5 catalogue and run
  exports passed at 1024, 1440 and 1920 pixels. Unmocked isolated backend/UI boot
  also passed, with all seven Gold registry entries available.
- Consistent recovery database `PRAGMA quick_check`: `ok`.
- Working and staged diffs passed whitespace checks. Owned acceptance servers and
  browser processes were stopped; the user's original application was untouched.

These results cover the integrated application and the final queue regression
correction. No MT5 orders were submitted. Checkpoint 1 is verified; subsequent
execution/deployment checkpoints remain outstanding as listed above.
