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

## Checkpoint 2 progress: read-only executable-price preflight

Development continues in the original directory on `feature/mt5-demo-execution`.
Verified integration commit `822abd9` was fast-forwarded onto local master; recovery
branches and the feature worktree remain. Nothing was pushed.

Added `backend/app/brokers/mt5_execution_preflight.py` and its deterministic test
module. The helper requires actual demo account classification, matching account
identity/currency, terminal/account trading permissions, supported protected market
entries, a non-crossed quote no older than five seconds (future quotes rejected),
price tick alignment, and broker minimum stop distances measured from the closing
side of the spread. It reuses existing broker-calculated lot/margin sizing with
current executable ask/bid and checks account binding again after calculations.
It calls neither order_check nor order_send and is not exposed as authorization.

Validation: **75 passed**, one existing Starlette deprecation warning, in the
preflight, execution-ledger, sizing and account suites (11.10 seconds). This
includes **33 new preflight cases**. The first targeted run caught a changed
adapter account binding during calculation; the final identity check was corrected
and the entire targeted group rerun successfully. Whitespace check passed.
The full 1,601-test integration result above predates this additional module;
no new full-suite/build claim is made for this incremental backend-only step.

Still required before Checkpoint 2 is complete: account-wide risk limits,
durable authorization/submission transitions, uncertainty reconciliation,
broker-confirmed protections and modification/closure, terminal dry-run acceptance.
The new helper is internal groundwork, not a wired gateway. No orders were sent,
no application routes changed, and no database migrations were added in this step.

Official references consulted for native account/symbol restrictions and request
semantics:
- https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py
- https://www.mql5.com/en/docs/constants/environment_state/accountinformation
- https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants

### Checkpoint 2 continuation: account-wide risk assessment and audit

Added a strict deterministic risk evaluator and durable, bounded assessment audit
in the existing execution ledger. It checks demo/account/currency identity,
complete reconciliation, five-second observation freshness, UTC risk-day and
strategy/session identity, unresolved submissions, permitted symbols, per-trade
risk, available margin, account-wide position and gross-exposure limits, daily
loss budget and session entry count (default one).

The conservative daily budget uses gross realized losses including costs, floating
losses, remaining open stop risk, pending stop risk and proposed trade risk.
Profits do not replenish this budget. Pending entries count toward position and
exposure limits. Monetary facts must already be in account currency; unknown facts
must reject evaluation, never become zero. Decimal comparisons protect boundaries.
This rule must be disclosed in deployment configuration before execution approval.

Assessments are diagnostic only: neither a passing record nor a restored record
arms a policy or reserves risk. The actual gateway still needs serialized
account-wide observation/reservation/submission and broker reconciliation. Native
account-risk collection/conversion is not wired yet. No public route accepts these
risk totals. Research scopes cannot write assessments, and superseded processes
cannot append them. Existing authorization remains disabled.

Storage: one additive table, `mt5_execution_risk_assessments`, created lazily by
`MT5ExecutionLedger`, alongside its existing tables. Stores validated allowlisted
facts, policy reference, proposal, decision/reasons and evaluation timestamp. No
existing user database was explicitly migrated or rewritten by this development.

Changed files:
- `backend/app/brokers/mt5_execution_ledger.py`
- new `backend/app/brokers/mt5_execution_risk.py`
- new `backend/tests/test_mt5_execution_risk.py`
- this handoff

Verification: **42 new tests**; focused execution/preflight/sizing/account group
**117 passed**. All `tests/test_mt5*.py`: **185 passed**, one existing Starlette
warning, 19.32 seconds. `git diff --check` passed. No frontend changes; no fresh
frontend build or full backend result is claimed for this increment. No native
order operations or real-terminal dry runs were performed.

Next: collect complete broker account-risk observations, implement serialized
durable submission/uncertainty reconciliation, protective-order verification and
mocked gateway acceptance before terminal dry-run and demo authorization UI.
Checkpoint 2 remains in progress; Checkpoints 3-6 remain as described above.

### Checkpoint 2 continuation: native read-only account-risk observation

Added `backend/app/brokers/mt5_risk_observation.py` and
`backend/tests/test_mt5_risk_observation.py`. The collector uses the existing
adapter's terminal lifecycle (caller must hold terminal/profile locks), reads
all positions and pending orders, and reads the UTC day's deals. It includes
manual/other-strategy exposure, negative trading P&L and individual fees,
commissions and swaps; deposit/withdrawal principal is excluded. Unsupported
separate cash operations reject, rather than silently dropping charges.

Remaining stop risk uses native `order_calc_profit` in account currency. Gross
notional currently supports only same-account-currency Forex and CFD calculation
modes using broker contract size. Futures, unsupported calculation modes and
currency conversions reject. Missing/invalid stops, unknown pending-order types,
missing/duplicate/oversized history, stale/crossed quotes, identity changes and
structural changes between repeated broker reads all reject. Collection takes a
bounded observation window and uses the lower observed equity/free margin.
These remain sequential observations, not an atomic broker snapshot.

The returned strict risk-facts object always has `reconciled=False`: broker rows
alone do not establish durable intent reconciliation. Tests demonstrate that the
risk evaluator therefore rejects entry until the separate reconciliation gate is
implemented. This collector is internal, not yet wired into a public gateway or
submission route. It calls neither order_check nor order_send.

Validation: **34 new tests**; all `tests/test_mt5*.py` **219 passed**, one existing
Starlette warning, 26.62 seconds. A first test found floating-point multiplication
noise in gross notional; calculation now uses Decimal multiplication before
conversion to the API numeric representation. The complete MT5 suite passed after
that correction. No frontend/application-route changes or schema additions in
this increment. No fresh full-backend/build or real-terminal acceptance claim.
No credentials were read and no broker orders were sent.

Official references:
- https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants
- https://www.mql5.com/en/docs/python_metatrader5/mt5historydealsget_py

Next required work remains the serialized durable submission/reconciliation
coordinator, wiring these observations and preflight into that gateway, protective
order verification/management, mocked end-to-end acceptance and terminal dry run.
Checkpoint 2 is not complete. Existing application workflows remain unchanged.

### 20 October: durable per-account operation guard

Added an account-wide operation guard to the existing execution ledger. SQLite
serializes acquisition across strategies/processes; no transaction remains open
during broker IO. Successful operation releases its own token only. Exceptions,
cancellation and process death retain the account for reconciliation. Restart
marks retained guards RECONCILIATION_REQUIRED and fences the old owner; no timeout
or automatic takeover can silently permit a retry. Guard acquisition is demo-only
and forbidden in Research Agent scope, but still grants no submission permission.

Storage: additive lazy table `mt5_execution_account_guards` (account key, process
owner, operation token, state and timestamp). No production database initialization
was performed in this increment. Existing intents and risk records are preserved.
Explicit recovery/reconciliation remains to be implemented; retained guards cannot
yet be cleared through an API. The guard is internal and not wired to live order
submission. Existing authorization remains disabled.

Verification: **11 new tests**, including an actual child process exiting via
os._exit while holding a guard. Focused authority/ledger tests **26 passed**.
All `tests/test_mt5*.py`: **230 passed**, one existing Starlette warning, 22.86s.
No frontend changes or fresh frontend/full-backend verification in this increment.

A local read-only terminal acceptance was attempted without reading credentials
or .env, using the existing logged-in terminal. It stopped at account verification:
`MetaTrader 5 account environment does not match this profile` for the required
demo environment. This is NOT a passed demo dry run. It did not proceed to risk
observation and sent no orders. The native proxy prohibited order_send,
order_check, login and symbol_select. Sanitized evidence is in ignored
`.ledger-test-artifacts/backend/mt5-risk-readonly-acceptance.json`.
The user must select a verified demo account in the terminal before demo-terminal
acceptance can pass; do not change accounts automatically.

Changed: `backend/app/brokers/mt5_execution_ledger.py`, new
`backend/tests/test_mt5_execution_authority.py`, and this handoff.
Checkpoint 2 remains in progress: submission/result state transitions, explicit
reconciliation/recovery, protective-order verification/management, end-to-end
mocked gateway tests and successful demo-terminal dry run remain outstanding.

### Priority MT5 Journal repair completed (20 October)

See `BROKER_CONNECTIONS.md`, MT5 history cutoff repair, for diagnosis, bounded
algorithm, limits and exact live acceptance results. The connected live account
was used strictly read-only: 11 missing closed trades imported, 32 existing Journal
records unchanged, repeat sync zero duplicates. 291 focused broker regression
tests passed. This is a separate repair commit; demo execution remains disabled.
The underlying discrepancy is broker deal epochs ahead of the host, not a seconds/
milliseconds conversion error. The code preserves reported timestamps and does
not assert a verified broker timezone correction.
