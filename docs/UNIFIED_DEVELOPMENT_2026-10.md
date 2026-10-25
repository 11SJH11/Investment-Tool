# Unified Ledger development — 19 October 2026

## Latest checkpoint: 25 October T02 saved-run drafts

See [MT5 DEMO automation status](MT5_DEMO_AUTOMATION.md) for the verified T02 parity,
immutable unarmed deployment drafts, operator authentication, same-origin API fix
and safe Fedora installer foundation. Full backend: 2,104 passed / 41 skipped.
Actual submission/management/worker integration remains unfinished. The user now
requests DEMO activation once technical acceptance passes; the Windows LIVE profile
must remain ineligible. Continue gateway/protection/recovery, not another draft-only
handoff. Preserve Telegram and both read-only bridges. No production changes yet.

## Previous checkpoint: 25 October account observations and diagnostic fallback

Research coordinator failures now have a bounded sanitized file fallback independent
of SQLite. Algo Trading has persisted real account observations, explicit read-only
refresh, equity history, paginated positions, account-switch guards and separate
DEMO/LIVE/currency totals. See [account observations](ALGO_ACCOUNT_OBSERVATIONS.md).
Full backend: 2,083 passed / 41 skipped (565.77s); frontend 145 passed; production
build passed (181 modules). No broker orders, paid calls or production DB changes.

New active brief: attachment `e8caffa6-52db-414c-aa36-c60c4846e6ff` requests the full
DEMO automated trading system, with T02 `gold_ifvg_v2_fvg_ratio_020` first, inherited
from saved runs. Existing T01 runtime/policies are diagnostic-only. Build safe staged
deployment/evaluation/execution/recovery/attribution/UI, preserving frozen rules.
Include a Fedora worker installer/updater; do not restart Telegram, LIVE bridge or
backend, or alter production data during development. User reports both read-only
bridges working after reboot. Actual broker submission/production rollout still
requires separate explicit approval and genuine DEMO safety acceptance.

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
   safe artifact cleanup. SQLite progress contention is repaired (see 21 October
   closeout below); the original historical exception was not retained, and
   full-range performance remains a separate investigation.
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

### Main roadmap resumed: positive-evidence order reconciliation

Added internal `mt5_execution_reconciliation.py` and 17 deterministic tests.
The classifier requires an explicit broker order ID, matching demo account,
canonical execution identities, complete evidence and verified remaining position
volume/protection. It distinguishes filled/partial protected positions, closed or
partially filled-then-closed orders, unverified protection, conflicting evidence
and unresolved submissions. Empty history or a missing broker order ID never
permits a retry. Another entry order netted into the position is rejected rather
than attributed to this strategy. It neither submits orders nor clears account
guards; gateway wiring, durable result recording and protection actions remain.

Final combined MT5/broker/TradeLocker/execution regression result: **308 passed**,
one existing Starlette warning, 29.43s. Four initial new tests constructed invalid
canonical executions and failed before reaching the classifier; corrected them to
exercise invalid native position quantities, then reran the whole group.

User input requested for the upcoming real demo acceptance: use a separate demo
terminal, explicitly switch the current terminal later, or defer terminal
acceptance. The current live TradeQuo account remains unchanged and is suitable
for read-only Journal sync only. No demo authorization or order submission has
occurred. Checkpoint 2 remains incomplete; the separate Journal repair is complete.

### Separate demo terminal verified (20 October)

User supplied `C:/Program Files/Trade Quo MT5 Terminal/terminal64.exe` for demo
acceptance. A read-only connection verified both the terminal installation path
and native demo account classification. Terminal connected; XAUUSDs available,
Forex calculation mode and profit currency matching account currency. Account-risk
observation succeeded: zero open positions and zero pending orders. It correctly
remains unreconciled (no execution gateway approval implied).

Native terminal reports `trade_allowed=False` and `tradeapi_disabled=False`.
Algorithmic trading is currently disabled; leave it unchanged until explicit demo
execution acceptance is ready. No login/account change, credential read, order
check or order send was performed. The live terminal was not targeted. Sanitized
local evidence: `.ledger-test-artifacts/backend/tradequo-demo-readonly-acceptance.json`.
This resolves the missing demo-terminal path/identity prerequisite, not the remaining
submission gateway, protection management or end-to-end execution requirements.

### Order preparation and expanded requested scope (20 October)

New internal `mt5_order_preparation.py` composes fresh demo preflight, native
symbol execution/fill modes, broker-supported FOK/IOC selection, protected SL/TP
request construction and non-executing `order_check`. Market Execution requests
omit price; other supported modes include executable bid/ask. Identity and quote
age are rechecked after validation. Returned broker codes are allowlisted numeric
facts; native comments/errors are not exposed. Every result remains execution
-disabled, and there is no order_send call. This still needs durable gateway and
account-wide risk wiring; it is not submission authorization.

Installed-package inspection found Python MT5 omits SYMBOL_ORDER_* and
SYMBOL_FILLING_* flag constants. Corrected preflight/preparation to use documented
symbol bitmask values (distinct from exported ORDER_FILLING request enums). Added
16 deterministic tests, including absence of those constants, broker rejection,
account switch, expired quotes and no-order guarantees. Final combined
MT5/broker/TradeLocker/execution tests: **324 passed**, one existing Starlette
warning, 37.68 seconds. No frontend changes/build in this increment.

Real demo check: Algo Trading is enabled. XAUUSDs initially had no subscribed
quote; enabled Market Watch subscription only after verifying the exact separate
terminal path and native demo classification. No login changes or order sends.
Fresh quotes became available, but quote time was 10,798.592 seconds ahead of UTC.
Preparation correctly rejected freshness, so native order_check was not reached.
Evidence: `.ledger-test-artifacts/backend/mt5-demo-order-check.json`.
This is a remaining acceptance blocker, not a successful broker-check claim.

Need broker-confirmed timestamp semantics, UTC offset and DST rule for the
specific demo server before normalizing execution quotes/session candles. User
was asked for the policy/documentation. Do not silently apply a permanent -3h
shift or alter existing saved research/Journal timestamps. TradeQuo's ZERO policy
mentions GMT+3 but alone does not establish this server's year-round DST rules:
https://tradequo.ae/company/faq/zero-low-liquidity-risk-protection
Native non-executing check reference:
https://www.mql5.com/en/docs/python_metatrader5/mt5ordercheck_py

User additionally requested, after the existing roadmap:
1. Trade screenshots/annotations across Journal/manual/broker, backtest and
   forward trades: background deterministic chart rendering, Context/Entry/Exit
   and optional full path; immutable base images with separately versioned
   text/arrows/lines/zones/circles/labels; thumbnail/lazy viewer/editor; retries,
   bounded backfill, clean/annotated exports and Research Pack manifests;
   repository/app-owned storage, safe cleanup, performance/browser acceptance.
   Full attachment: d098c449-2997-4400-a33e-83801dad6d3a/Pasted text.txt.
2. Dedicated main-nav Algo Trading monitoring, reusing the planned deployment
   backend rather than a second execution service. Full dashboard brief received.
   Phase A: actual demo accounts/deployments/heartbeats/positions/trades, metrics,
   charts and persistent events. Phase B: supported authenticated controls,
   risk/notifications, account snapshots and matched backtest comparisons.
   Phase C: multiple strategies/accounts, attribution and shared account risk.
   Separate currencies/environments, deduplicate shared account balances,
   distinguish simulated from actual performance, expose sample N, never label
   saved enabled configuration as a running process or fabricate missing data.
   No controls that exceed verified backend capabilities; no orders as part of
   dashboard development. Live TradeQuo must remain ineligible for automation.

Screenshot and Algo UI implementation has not begun: preserve the requested
sequence, reuse existing attachment/render/export/design-system/notification
facilities when reaching them. The Algo page will be the monitoring surface for
planned deployments, not a competing dashboard. Existing Checkpoints 2-6 remain
incomplete as already listed. No additional strategy rules were changed.

### 2026-10-21 priority interruption: structural Docker execution repair

Paused the above roadmap at its verified, execution-disabled boundary (83b79a7).
User requested the Research Agent Docker repair first, then continuation.
No active user campaign will be restarted, cancelled or modified by acceptance.
TradeQuo's supplied Client Services Agreement section 3.1 confirms UTC+2 winter /
UTC+3 summer for company hours; it does not specify the demo server's DST switch
dates or Python timestamp representation. Verified the accessible PDF on 21 October:
https://www.tradequo.com/fsu/wp-content/uploads/2024/09/Client-Services-Agreement-TQ-FSU.pdf
The supplied 2022 terms PDF could not be retrieved by the documentation tool.
Read-only native demo verification succeeded: exact separate terminal path and
native demo classification, connected terminal, three XAUUSDs raw tick samples.
Offsets ahead of UTC receipt were 10800.174, 10800.175 and 10800.276 seconds.
This is strong evidence of a current server-aligned epoch on this installation,
not proof of a year-round DST schedule. Evidence (server name, raw milliseconds,
UTC receipt; no login/credentials):
`.ledger-test-artifacts/backend/mt5-demo-clock-20261021.json`.
No login changes, trading settings changes or orders were made. Automated entry
remains disabled. Need broker confirmation of this server's exact transition rule
(US, European, or another calendar), effective dates and whether historical quote
and bar epochs use the same convention before implementing normalized execution.
Do not hardcode a permanent UTC+3 offset or infer a DST schedule from one quote.
MT5 gateway/deployments, remaining CP2–6, screenshots/annotations and Algo Trading
remain pending in the order above. No test orders are authorized for this work.

Docker diagnosis: the Linux daemon is reachable; exact tag inspection reports
`No such image` while image listing and inspection by immutable ID succeed on
the same daemon. The installed sandbox fingerprint was also stale. Repair uses
verified exact-tag-to-ID resolution (no alternate image) and rebuilds only the
allowlisted sandbox context. Repair verification is complete:

- Full backend: 1,773 passed, 41 skipped, 588.16s.
- Combined real-Docker security, research loop, structural campaigns and Gold
  preparation/archived-source acceptance: 59 passed, 496.54s.
- Frontend: 139 passed. Documented isolated production build: exit 0, 168 modules.
- Diff check passed. Zero Ledger research containers; six unrelated stopped
  containers retained. User campaign states remain PREPARATION_FAILED/CANCELLED.
- Existing Starlette deprecation and frontend chunk-size warnings remain.
  Standard Vite builds had intermittent existing-file resolution failures;
  documented dotenv-free runner builds passed twice. No new browser acceptance.

Full diagnosis, changed-file summary, exact commands and manual instructions:
[major update repair appendix](RESEARCH_AGENT_MAJOR_UPDATE_2026-10.md#21-october-structural-docker-execution-repair).
No migration, frozen-strategy change, paid model call, order or user data rewrite.
The user backend was not restarted. Restart normally when no campaign is active
to activate this backend repair. Structural research is technically verified with
deterministic/mocked-model tests; provider history and model quality remain
external acceptance, not guarantees of profitable research.

Next roadmap boundary: obtain/independently verify this demo server's precise DST
rule before quote normalization and safe submission acceptance. Continue the
remaining gateway/deployment work under execution-disabled defaults, then CP3–6,
screenshots and Algo Trading in the recorded order. The read-only clock evidence
above is the resumed roadmap work; those larger features are not complete.

### 21 October: backtest progress contention repair

User reported frequent `[storage]` failures. Read-only inspection found the failed
combined Gold job stopped at recorded progress 248,064/409,971 bars, while two
other Gold variants subsequently completed. The previous error handler discarded
the underlying exception, so the historical failure cannot be conclusively
attributed from its saved message alone. No original jobs/results were changed.

Reproduced a concrete matching failure path using a real SQLite WAL writer lock:
an optional progress write exceeded the default five-second timeout and raised
`OperationalError / SQLITE_BUSY`, aborting the simulation. This was misclassified
as a disk/cache problem. No disk-space exhaustion was involved in the reproduction.

Progress writes now use zero lock-wait and skip only SQLite BUSY/LOCKED errors.
Successful progress writes are throttled to twice per second, plus phase/final
updates. Every callback still checks cancellation/authorization. Result persistence,
cancellation and completion writes remain mandatory; disk/corruption errors still
fail. Progress connections close explicitly; failed connection setup also closes.
Mandatory contention errors now use `[database_busy]` with an accurate explanation.
No migrations, trading-rule changes, result rewrites, or provider calls.

Verification:
- Before fix, real-lock regression failed with `OperationalError / SQLITE_BUSY`.
- Focused queue/contention tests: 19 passed, including cancellation, critical-write
  failures, SQLite extended codes, error redaction and progress throttling.
- Full backend: **1,780 passed, 41 skipped**, 545.52s; existing Starlette warning.
- Actual cached OANDA midpoint data, combined Gold strategy, 9–15 September 2025:
  completed 6,881 1m bars / 461 15m bars, four trades, 6.39s. Separate database.
  This window includes the date at the original saved progress point.
- Exact original date-range/configuration rerun used a separate database and no
  provider calls. Cancelled at its 900-second verification cap, 147,968/409,971
  bars, error null, no saved run. This is NOT full-range completion or a speed fix.
- Diff check passed. Frontend unchanged; no new frontend build/browser run.

Local evidence: `.ledger-test-artifacts/logs/backtest-contention-full.log`,
`backtest-contention-real-cache.json`, `backtest-contention-full-range.json`.
Changed: `backend/app/core/safe_errors.py`, `backend/app/services/backtest_jobs.py`,
`backend/app/storage/database.py`, `docs/BACKTEST_WORKFLOW.md`, this handoff.
New: `backend/tests/test_backtest_progress_contention.py`.

Activate by restarting the backend normally when no user run/campaign is active,
then retry the failed job. Do not delete the database/cache or historical results.
The running user backend was not restarted by this repair. The user subsequently
requested resumption of the broader roadmap after this focused repair.

### 21 October: durable MT5 reconciliation observations

Resumed CP2 after storage repair `d2ad68b`. The existing positive-evidence
classifier now has an internal durable recording interface on MT5ExecutionLedger.
Observations are attached to a known intent, deduplicated by their allowlisted
content, and retained across restart. Partial/closed, conflicting and incomplete
observations remain inspectable with bounded history reads. Old process writers
are fenced; Research Agent callers cannot write observations. Native provider
metadata/comments are not copied into this log.

Additive initialization creates `mt5_execution_reconciliations` (id, intent_id,
document). No existing rows are rewritten, no Journal records are touched, and
the running user's database has not been initialized or migrated during testing.

This is diagnostic evidence, **not verified attribution or submission authority**.
A draft matching a broker order is not proof that Ledger submitted it. Thus a
positive result never changes a draft's state, enables a policy, clears an
account guard, or permits retries. No public API accepts broker facts. The future
gateway must supply a durably established order identity and complete snapshot.

Changed: `backend/app/brokers/mt5_execution_ledger.py` and this handoff.
New: `backend/tests/test_mt5_durable_reconciliation.py`.

Verification: all `tests/test_mt5*.py` on this final tree: **284 passed**, 32.53s,
including 15 new durable-observation cases. Existing Starlette deprecation warning
only. `git diff --check` passed. Frontend unchanged; no new build/browser run.
The prior full-backend result (1,780 passed, 41 skipped) predates this addition;
it is not presented as full-suite verification of this tree.

Remaining: serialized submission/uncertainty state machine, authoritative broker
identity linkage and account-wide recovery, integration of native preparation and
risk observations, protection management, mocked end-to-end gateway acceptance,
then demo-terminal dry run and explicit authorization. The server-specific DST
transition rule remains unverified; no fixed UTC+3 conversion was introduced.
CP2 is not complete. T01 deployment, screenshots and Algo Trading follow in the
previously recorded order. No orders, account switches or terminal changes made.

### 21 October: write-ahead MT5 attempt lifecycle

Continued from `cff3a02`. Added internal durable attempt/receipt primitives for
the future submission coordinator. `begin_attempt` requires a demo draft and its
current account guard. In one transaction it creates a unique attempt, marks the
intent SUBMISSION_UNCERTAIN and retains the account for reconciliation. Normal
context-manager completion must not release this retained guard. Process death
before any receipt therefore cannot make the draft available for another send.

Receipts retain only the numeric broker return code and optional canonical order
ticket. They are immutable and idempotent; an order ticket cannot be attached to
two attempts on the same account. Different accounts may reuse ticket numbers.
Neither success nor rejection codes establish a fill, protection or retry right.
Emergency stop prevents new attempts but allows the original owner to retain a
late receipt; restart fences that owner and leaves recovery blocked. Research
callers cannot create attempts or record receipts.

Additive table: `mt5_execution_attempts` (id, unique intent_id, account_key,
broker_order_id, document), with account/order uniqueness. No destructive
migration, Journal rewrite, running-backend restart or terminal operation.

Changed: `backend/app/brokers/mt5_execution_ledger.py` and this document.
New: `backend/tests/test_mt5_execution_attempts.py`.

Verification: all `tests/test_mt5*.py`: **301 passed**, 29.54s, including 17 new
attempt tests (one actual subprocess-death case). Existing Starlette warning only.
`git diff --check` passed. Frontend unchanged; no new frontend build or full-backend
run for this bounded internal change. No provider calls or orders were submitted.

These are **internal persistence primitives, not a working submission gateway**.
There is no native send call, public submission endpoint or arming path.
`authorize_submission` remains unconditionally disabled. Still required: compose
authorization, fresh native preparation, reconciled account risk, attempt marker
and broker transport; validate exact request provenance; implement account-wide
recovery and protection management; then mocked end-to-end and demo acceptance.
The previously recorded server DST/timestamp blocker and later roadmap remain.

### 21 October: guarded read-only coordinator

Continued from `8abad42`. New internal `mt5_execution_coordinator.inspect_intent`
composes existing native preparation, immutable draft checks, account-wide risk
observation and persisted risk assessment under the durable account guard.
It accepts no frontend-supplied exposure, loss totals or reconciliation flag.
The caller must already own the terminal/profile lifecycle locks; this helper
does not initialize or switch terminals and is not a public endpoint.

Fresh price/quantity must match the stored draft exactly. Rejected broker checks
produce a diagnostic rejection without inventing an assessment. Missing history,
account mismatch, quote expiry and changed sizing fail closed. Manual positions
consume the same account risk budget. Uncertain attempts from other strategies
on the same account are counted from durable storage. Until proper session
attribution exists, all historical attempts for that strategy are conservatively
counted; this basis is explicitly returned, not represented as session accuracy.

Successful diagnostics retain `reconciled=False` and `execution_enabled=False`.
They do not create submission attempts, alter drafts, clear recovery guards or
call order_send. No arming controls were added. As with existing guard operations,
a failed diagnostic retains the account for recovery; an ordinary completed
diagnostic releases its guard. This conservative behavior needs the forthcoming
explicit recovery path before exposing the helper to normal users.

New files: `backend/app/brokers/mt5_execution_coordinator.py`,
`backend/tests/test_mt5_execution_coordinator.py`. Updated this handoff.
No database migration, frontend change, terminal operation or real order.

Verification: all `tests/test_mt5*.py`: **313 passed**, 45.40s, including 12 new
coordinator tests. Existing Starlette warning only; `git diff --check` passed.
Full backend/frontend suites and frontend build were not rerun for this internal
addition. Previous full-suite results must not be treated as results for this tree.

Still remaining: verified timestamp/session interpretation, complete account
reconciliation/recovery, authorized broker submission orchestration and protection
management, then end-to-end demo acceptance. CP2 remains incomplete; no claim
that T01 is running. Later deployment, screenshot and Algo Trading work is unchanged.

### 21 October: recover finished read-only diagnostic failures

Continued from `1169895`. The coordinator now explicitly acquires a read-only
account guard. `begin_attempt` rejects such guards at the durable ledger boundary.
Finished failed checks retain typed evidence, so the internal
`recover_failed_diagnostic` method can release their guard without pretending to
reconcile a submitted order. Recovery is explicit, transactional, owner-fenced
and audited; it does not arm policies or undo emergency stop.

Recovery refuses active checks, interrupted checks without finished-failure
evidence, legacy/untyped guards, live policies, Research callers and accounts
with any durable attempt (including another strategy's). No elapsed-time expiry
or generic force-unlock was introduced. A normally completed diagnostic removes
its temporary marker; failed/recovered markers remain available for audit.

Additive initialization table: `mt5_execution_readonly_guards` with token,
account_key, state, created_at and recovered_at. Existing guards are not backfilled
as safe. Running user data/terminal were not changed or restarted. No API endpoint,
frontend change, broker order or account switch.

Changed: `backend/app/brokers/mt5_execution_ledger.py`,
`backend/app/brokers/mt5_execution_coordinator.py`, this handoff.
New: `backend/tests/test_mt5_diagnostic_recovery.py`.

Verification: all `tests/test_mt5*.py`: **322 passed**, 34.03s, including nine new
recovery tests. Existing Starlette warning only. `git diff --check` passed.
Frontend unchanged; no new production build or full-backend run for this step.

### 21 October: demo permissions and receipt-bound recovery evidence

Read-only native verification against the exact separate terminal
`C:\Program Files\Trade Quo MT5 Terminal\terminal64.exe` confirmed demo mode,
connected=true, terminal trade_allowed=true, tradeapi_disabled=false, account
trade_allowed=true and trade_expert=true. No login/account changes, orders or
settings changes. Native shutdown closed the Python connection, not the terminal.
**MT5 Algo Trading permission is enabled; Ledger automated submission is not.**
T01 is not running merely because these native permission flags are enabled.

Added internal `reconcile_attempt`: order identity comes only from the immutable
stored attempt receipt. No caller-supplied replacement ticket is accepted. Missing
receipts/order IDs remain unresolved even when other matching-looking fills exist.
The canonical classifier still checks account/environment, fills and protection.
Observation history and the attempt's latest observation pointer are saved in one
transaction. Older snapshots remain in history without replacing the newer pointer.
Restart preserves this evidence and fences the previous writer.

This does not release account guards, change uncertain attempts into authorized
retries, or claim verified attribution. Complete/fresh broker snapshot collection
and account-wide recovery remain required; a closed/protected observation alone
does not prove those broader conditions. No new schema or frontend changes.

Changed: `backend/app/brokers/mt5_execution_ledger.py`, this handoff.
New: `backend/tests/test_mt5_attempt_reconciliation.py`.
Verification: all `tests/test_mt5*.py`: **331 passed**, 37.16s, including nine new
receipt-bound cases; existing Starlette warning only. `git diff --check` passed.
No full-backend/frontend rerun or build for this internal change.
Remaining: broker snapshot/recovery orchestration, submission/protection workflow,
verified server-time transition rule, then T01 acceptance and later roadmap.

### 21 October: broker recovery snapshot verification

Added `backend/app/brokers/mt5_recovery_snapshot.py` and 19 tests in
`backend/tests/test_mt5_recovery_snapshot.py`. Uses canonical MT5 execution
history with two matching observations of executions, positions and pending
orders; bounded counts/time and account/UTC timestamp checks fail closed.
Receipt-bound observations can now be collected for all attempts on the selected
account. No account release, submission, terminal switching or Journal writes.

Final full verification: **1,861 backend passed, 41 skipped**, 564.79s;
**139 frontend passed**; isolated production build **passed**, 168 modules,
exit 0. The first build encountered intermittent resolution of an existing
watchlist.js; retries passed without source changes. Existing chunk-size and
Starlette warnings remain. Logs: `.ledger-test-artifacts/logs/mt5-recovery-*`.
No new browser/Docker acceptance was performed in this step.

The user has added a Research Agent audit/progress brief. Read-only inspection at
18:14 UTC found campaign `15b7318e-94d7-4585-bbc6-1f1f4336dee8` already terminal:
DEVELOPMENT_COMPLETE, but its sole family FAILED with baseline_compute_deadline.
Job `49b0af9a-df72-48dd-ad1b-f6a059f46c72` was cancelled at 209,408/790,767 bars,
no saved run. The coordinator recorded failure at 17:52:10 UTC and completion at
17:52:15 UTC. No user campaign was cancelled/restarted/edited by this inspection.
New work must distinguish failed closeout from success and expose actual job
progress without touching campaign assumptions or holdout.

### Current continuation: Research Agent audit and progress

See [the current audit/evidence and remaining-work list](RESEARCH_AGENT_AUDIT_2026-10-21.md).
First monitoring slice implemented: real baseline/reference queue progress,
terminal family failure outcome, conservative suspected-stall indication, no fake
ETA. 75 focused backend tests, 141 frontend tests and production build passed.
The full technical audit, operation/activity monitoring and performance diagnosis
are still in progress. User campaigns and running services were not restarted.
The separate MT5 clock probe confirmed advancing ticks around +3 hours, but did
not verify a DST schedule or grant execution permission.

Remaining: recovery for potentially submitted orders still requires authoritative
broker reconciliation; this diagnostic recovery is not that acceptance. Actual
submission, protection management, verified server timing and T01 deployment
remain disabled/incomplete, followed by screenshots and Algo Trading as before.

### 2026-10-22 verification and reconnect checkpoint

Full backend verification completed: **1,898 passed, 41 skipped** (585.20s).
The nine newer clock-diagnostic tests passed separately. Current frontend:
**144 passed**, production build passed on retry; existing chunk warning and
intermittent Windows resolver issue remain. Four real Docker smoke tests passed;
no Ledger containers remained, and unrelated stopped containers were untouched.
Production fixture browser checks passed at 390/1024/1440/1920px before the
subsequent reconnect repair. See the audit document above for evidence scope.

The FVG detector now avoids per-row pandas Series creation, with 26 parity tests;
the measured speedup applies only to the isolated detector, not an entire campaign.
Campaign report polling now survives transient failures with bounded serial
backoff, last-refresh time and a stale-data warning. No campaign mutation retries.
The read-only MT5 clock CLI measures a current offset, never authorizes execution
or asserts an unobserved DST transition rule. No schema migration or user backend
restart was performed. Research audit/operation instrumentation and the broader
MT5/screenshots/Algo dashboard roadmap remain incomplete.

### 2026-10-22 activity paging and numeric queue evidence

Campaign activity is now bounded to 50 events per report with cursor-based older
pages and a campaign/event index; historical events remain intact. UI history
failure/retry and latest/older navigation are verified. Numeric control/variant
current-attempt progress is exposed from durable queue records, without payloads,
results or unrelated project data. Model/Docker operations are not counted as
simulations. Tests: **80 focused backend**, **144 frontend**, production build and
fixture browser checks at 390/1024/1440/1920px passed. Full backend verification
has not been repeated for this incremental change. The audit above records scope.
Remaining: model/structural operation instrumentation and broader research audit;
MT5 submission/protection/timing acceptance, screenshots and Algo dashboard.

### 2026-10-22 model operation monitoring verified

Model roles now persist before dispatch. Returned numeric committee metering
survives authorization revocation during a call. The operation panel distinguishes
reservations, returned usage, estimated known cost and unknown cost. Process-local
coordinator cycle timestamps are separate from simulation progress. The audit
document contains inspected mechanisms, evidence and remaining limitations.

Final full backend run: **1,922 passed, 41 skipped**, 622.59s. Frontend: **144
passed**; production build passed (172 modules, existing chunk warning). Real
Docker security/lifecycle suite **22 passed**, sandbox research-loop suite **9
passed** (31 total, 183.79s). No orphan Ledger containers; six unrelated stopped
containers untouched. Fixture browser smoke passed at 390/1024/1440/1920px.
No account changes, orders, paid model calls or user backend restart.

Future research backlog (user request): Gold post-impulse range-rejection strategy,
R01–R05 variants. Define causal numerical rules and preregister one-variable
experiments later; no implementation or tuning during the current priority work.

### Genuine Gold baseline acceptance completed

The explicitly authorized corrected-FVG baseline completed on cached real OANDA
development history in **6,408.813s**, within its original **6,900s** allocation.
410 trades; original zero-cost / 300x assumptions unchanged. Existing failed
campaign preserved; no holdout/provider/model/order calls. Details, data-boundary
qualification and artifact digest are in the current Research Agent audit.
Added opt-in `backend/tools/verify_gold_campaign_baseline.py`; three safety tests
passed. This proves baseline completion, not complete paid research-loop acceptance.

### Algo Trading monitoring foundation

The main navigation now opens a read-only Algo Trading page backed by
`GET /algo-trading`. It projects MT5 connection sync evidence and saved execution
policies without opening a terminal or initializing an execution ledger. Policies
are explicitly NOT_DEPLOYED, never Running. Existing shadow deployments retain
their simulated identity, metrics and bounded recent trade history; account equity
is not pooled or inferred. Worker existence does not prove fresh evaluation.

This is a foundation, not completed T01 monitoring: no T01 worker, broker balance
snapshot history, attributed execution analytics, performance charts, notifications
or execution controls were added. T01 remains disabled. Protection/recovery and
verified session timing are still gates; no orders or account changes occurred.

Verification: 35 focused backend tests (including five monitoring cases), 144
frontend tests, production build, and fixture browser checks at
390/1024/1440/1920px passed. Browser checks cover read-only requests, stale state,
retry, reload and no overflow/runtime errors. An initial build hit the existing
intermittent Windows import-resolution failure; an unchanged retry passed.
No schema changes. The previous full backend count above predates this foundation.

### Docker progress and final verification

Persisted host bar counts now accompany Docker phase/lifecycle observations;
possible stalls are explicit and never trigger automatic retries. See the audit
for projection boundaries and remaining coarse phases.

Final complete backend run: **1,932 passed, 41 skipped, one deprecation warning**
in 630.55s. Frontend **144 passed**; production build passed (existing chunk-size
warning). Real Docker security/lifecycle and research-loop tests **31 passed**
in 192.89s. Browser fixture acceptance passed at 390/1024/1440/1920px for both
monitoring and campaign operations. No orphan Ledger containers remained; six
unrelated stopped containers were unchanged. No schema migration or real-service
restart. Initial full run found only a stale test schema, corrected before the
final run. User-generated strategy/export files remain untracked and untouched.

Next user-prioritized work: a read-only loopback Fedora/Wine MT5 bridge, preserving
the native adapter and requiring DEMO identity. Real Fedora discovery and sync
acceptance cannot be inferred from Windows/mock tests. Then continue execution/
protection/recovery, full Algo monitoring and screenshot annotations. Automated
execution remains disabled and no test orders are authorized.

### Fedora/Wine read-only bridge implementation checkpoint

Implemented the explicitly configured, disabled-by-default MT5 transport, an
authenticated IPv4-loopback service, strict read method/schema/size limits,
exclusive session leases, pinned DEMO identity before/after reads and a native-call
watchdog. Windows-native adapter behaviour remains the default. No database
migration, native account switch or order call was added. Journal uses the existing
reconciler/cursor model; partial/repeated imports and failure preservation were
tested through real local HTTP with a fixture terminal.

See [MT5 Linux bridge](MT5_LINUX_BRIDGE.md) for exact Fedora commands, user systemd
template, timestamp limitations and the temporary-database real acceptance checker.
The user will run Fedora acceptance; no SSH access was supplied. Therefore **real
Ledger DEMO discovery and Journal sync on Fedora are still pending**. Existing
direct Wine/MT5 connectivity evidence is not substituted for that acceptance.
Raw timestamps are preserved, not shifted by a guessed seasonal offset. Bridge
market-history research reads reject until UTC semantics are explicitly verified.

Verification: **412 MT5/broker tests passed**, **144 frontend tests passed**,
production build passed on unchanged retry, diff check passed. The preceding full
backend/Docker counts above predate the bridge changes. The next roadmap work
remains execution/protection/recovery integration, complete Algo monitoring and
screenshots/annotations, with automated execution disabled pending authorization
and verified timing. The R01–R05 research idea remains a future task.

### Monitoring continuation after bridge checkpoint

Algo Trading now exposes the latest 100 persisted, allowlisted MT5 recovery
observations. Selecting a preparation filters these observations to its policy.
Filled/remaining lots, observation completeness and receipt identity are shown;
historical protection evidence is explicitly not a current position snapshot,
strategy attribution, account release or trading authority. No execution ledger
is initialized by monitoring, and no terminal/native API is called.

Verification: **34 focused monitoring/recovery tests passed**, **144 frontend
tests passed**, production build and diff check passed. Fixture browser checks at
390/1024/1440/1920px passed, including stale/retry/reload, recovery evidence,
GET-only requests and no runtime errors/page overflow. No schema change. Full
T01 worker/protection runtime, complete analytics/dashboard and screenshots remain
unfinished; the bridge's real Fedora acceptance remains pending the user's run.

### Recovery history paging (23 October)

Replaced client-side filtering of the global latest 100 observations with a
read-only `/algo-trading/recovery` endpoint. Policy filtering precedes the page
limit, so a busy account cannot hide an older preparation's observations.
Exclusive row cursors preserve older pages when new observations arrive. Pages
are bounded to 100; the UI uses 50 and keeps one page in memory. Failed loads
retain the previous page and support retry; changing selection discards stale
responses. The existing overview projection remains compatible.

No new execution authority, broker calls, schema migrations or data deletion.
Verification: 36 focused backend tests, 144 frontend tests, production build,
diff check and fixture browser smoke at 390/1024/1440/1920px passed. Browser checks
include policy selection, older/latest, failure/retry, reload and GET-only access.
Full backend suite was not repeated for this bounded monitoring increment.
Outstanding work remains the Fedora acceptance/timestamp investigation, T01
runtime/protection/recovery orchestration, complete monitoring analytics and
screenshot annotations; trading is still disabled.

### Atomic account recovery (23 October)

Reproduced a partial-commit bug: if reconciliation of a later intent failed,
earlier intent observations from the same account pass remained committed. The
account recovery coordinator now delegates persistence to one ledger transaction,
including latest-reconciliation pointers. Native collection finishes before that
transaction. The selected account/currency and current process ownership are
rechecked inside it; observations remain receipt-bound and never release account
guards or authorize trading.

New regressions cover late classification failure, late SQLite write failure
with previous successful evidence preserved, separate account histories,
idempotent repeated recovery and a process restart during snapshot collection.
The original single-intent API retains its existing transaction behaviour.
No schema migration, real broker call, account change or order was performed.

This closes a persistence gap, not the complete T01 execution workflow. The
automatic runtime, protection orchestration, verified session timing, actual demo
acceptance, remaining analytics and screenshot annotations are still outstanding.
Large account recovery performance also needs acceptance before runtime deployment;
atomicity does not establish that a large historical recovery is inexpensive.

Final verification against this accumulated bridge/monitoring/recovery tree:
**1,963 backend passed, 41 skipped**, one existing deprecation warning, in
587.11s. Focused MT5/broker/monitoring suite **424 passed**. Frontend **144 passed**;
production build passed on unchanged retry after the known intermittent Windows
resolver error (174 modules; existing large-chunk warning). Diff check passed.
No real broker acceptance or Docker opt-in rerun is implied by these counts.

### Account safeguard monitoring and user bridge feedback (23 October)

The user reports that the MT5 bridge works well. Record this as user-reported
operational success, not independent evidence of verified tick/bar UTC semantics,
seasonal transitions or order-execution acceptance. No additional broker probe,
account switch or order was performed in this checkpoint.

Algo Trading preparation details now show persisted account guard state, the
all-history account attempt count and the latest recorded risk assessment:
pass/rejection reasons, observation time, UTC risk day and projected loss budget/
exposure in the policy currency. Shared-account counts are explicitly not additive;
missing evidence stays unknown. Historical passing diagnostics do not authorize
execution or imply current account risk/protection. Owner/guard tokens and raw
account facts are excluded. The projection uses three bulk queries independent of
preparation count and the existing overview reads a consistent SQLite snapshot.

Verification: **76 focused backend tests passed**, **144 frontend tests passed**,
production build passed on unchanged retry after the existing Windows resolver
failure. Fixture browser checks passed at **390/1024/1440/1920px**, covering the
new safeguard details plus stale/retry, history paging, reload and GET-only
requests, with no runtime errors or page overflow. `git diff --check` passed.
No migrations. The previous full-suite result (1,963 passed / 41 skipped) predates
this increment and has not been repeated here.

Still unfinished: persistent T01 runtime; verified market-data/session timing;
submission/protection/recovery orchestration and separately authorized demo order
acceptance; attributed broker performance/snapshots/charts/alerts and supported
controls; genuine model-driven campaign acceptance; screenshot annotations.
Automated trading remains disabled. No external input is required to continue
implementation and mocked verification of those components.

### Durable T01 completed-bar diagnostics (23 October)

Added an internal execution-disabled decision runtime for the unchanged
`gold_ifvg_v2_skip_23et` strategy. Existing registry/source archives,
StrategyContext and Market Concepts are reused; no broker execution behavior or
frozen Gold rules changed. Preparation pins a matching demo risk policy and
implementation identity. One-minute evidence and decisions commit atomically;
restarts replay persisted observations and reject divergence. Failed writes,
changed bars, gaps, source drift and concurrent frontiers fail closed.

The runtime requires an explicit verified-UTC input contract, starts at 20:00
America/New_York, constructs 15m bars only from all 15 completed minutes and caps
streams at 2,880 bars. It preserves Sunday/DST session interpretation, the 23:00
exclusion, next-minute eligibility and +0.68R management instructions. There are
no inferred fills, broker calls, order submissions or automatic continuation over
market closures. Attribution of supplied positions remains an internal caller
contract to be fulfilled by the future receipt-bound coordinator.

Two additive, internal tables (`mt5_t01_diagnostics`, `mt5_t01_decisions`) are
created only on explicit runtime construction. No user database initialization or
migration was performed. Algo Trading shows the latest prepared diagnostic
stream's saved frontier and signal separately from worker health/trades; policies
remain NOT_DEPLOYED and execution-disabled.

See [T01 diagnostic runtime](MT5_T01_DECISION_RUNTIME.md) for architecture,
verification instructions and limits. This is not the persistent polling worker
or a complete MT5 deployment. Outstanding work remains verified feed timing,
worker lifecycle/heartbeat, receipt-bound positions, submission/protection and
recovery integration, authorized demo acceptance, complete monitoring analytics,
genuine model-driven campaign acceptance and screenshot annotations.

Final verification on this checkpoint: **1,979 backend passed, 41 skipped**, one
existing Starlette/httpx deprecation warning, in 566.22s. Focused final T01/runtime
and monitoring checks: **24 passed** (including 13 new T01 cases). Earlier
runtime/Gold/recovery/coordinator regression selection: **69 passed**, before the
last monitoring case was added; the final full suite includes it. Frontend:
**144 passed**. Production build: passed first attempt, 175 modules, existing
large-chunk warning. Fixture browser smoke: **390/1024/1440/1920px passed**, including
diagnostic labels, stale/retry, paging, reload, GET-only and no runtime errors or
page overflow. Diff check passed. No real Docker suite or live broker/order
acceptance was rerun; opt-in skips are not claimed as passes.

### Read-only MT5-to-T01 observation cycle (24 October)

Connected the T01 diagnostic runtime to a bounded broker observation cycle using
existing profile locks and the native/bridge adapter. Only an explicitly selected
DEMO profile/account/currency and explicit terminal/bridge path are accepted.
The connection passes no login/password/server options that could switch native
accounts. Current connection, identity and flat-account facts are checked before
and after the read; no order, login or account-setting API was added.

The collector requires independently verified UTC semantics and a fresh raw UTC
quote. It retrieves only the latest completed minute plus the immediately prior
saved minute for overlap/revision validation. Missing, revised, duplicate,
shifted/future or malformed history fails closed. The forming right-edge bar is
excluded. MT5 tick-volume provenance and the selected profile are persisted with
the decision. No inferred broker offset, cached fallback or synthetic data exists.

The serialized cycle avoids another broker request for an already-recorded
minute. Missed minutes/clock rollback require explicit recovery, not historical
catch-up. Cancellation before/after collection and failed reads preserve the
frontier and release the profile/adapter lifecycle. A test found and fixed an
empty corrupted checkpoint bypassing the initial integrity guard; no native read
now occurs for that record. Quote freshness uses post-read receipt time so a quote
advancing during the call is not falsely classified as future.

This completes the internal observation-cycle connection, not the persistent
worker or automated execution. Open positions or pending orders currently block
this diagnostic collector until receipt-bound position attribution is integrated.
The five-second snapshot budget is validated after calls; it does not interrupt a
blocked native API. Existing bridge watchdog/timeouts remain unchanged. No real
broker calls, user DB initialization, orders or account changes were performed.
No new schema in this increment; existing diagnostic JSON gains allowlisted feed
evidence. Source fingerprints now include feed/poll code, so old diagnostic streams
must not silently upgrade. See MT5_T01_DECISION_RUNTIME.md for the current contract.

Remaining: independently verified broker timestamp semantics, persistent worker
lifecycle/heartbeat, broker position attribution, submission/protection/recovery
integration and separately authorized demo acceptance. Full monitoring analytics,
genuine model-driven campaign acceptance and screenshot annotations remain later
work. T01 remains NOT_DEPLOYED and automated execution disabled.

Final verification against this exact increment: **2,025 backend passed,
41 skipped**, one existing Starlette/httpx deprecation warning, in 585.61s.
Focused T01 feed/poll/runtime plus MT5 market-data/bridge checks: **96 passed**.
The new collector/poll tests add 46 deterministic cases to the preceding full
suite. Frontend: **144 passed**. Production build: passed first attempt with the
existing large-chunk warning. Diff check passed. No frontend code changed, so
browser smoke was not repeated in this increment; the prior fixture viewport
results remain historical evidence. No real broker or opt-in Docker acceptance
was rerun. Orders and automated execution remain disabled.

### Persistent T01 diagnostic worker (24 October)

Added the explicitly started, execution-disabled diagnostic worker and integrated
its construction/shutdown with application services. Startup creates additive
diagnostic/worker tables but never starts polling or contacts a terminal. Initial
observation waits for 20:01 New York; missing minutes are not backfilled. Account
leases, generation fencing and a decision-transaction commit guard reject late
results after stop, shutdown or explicit stale-owner takeover. One active stream
per account is enforced by storage. No Journal records or policy permissions are
changed; development checks used temporary databases only.

Algo Trading now displays actual local thread liveness, persisted heartbeat and
last-decision/error evidence. Interrupted workers require recovery; persisted
state does not become a Running deployment after restart. Stop is distinct from
closing/protecting positions. Blocked native reads can outlive the two-second join
budget and remain visibly STOPPING; they cannot subsequently commit decisions.
There is no public activation endpoint or automatic resume.

The new additive table is `mt5_t01_workers`, with a partial unique active-account
index. Worker implementation joins the immutable diagnostic source fingerprint;
old streams cannot silently adopt changed code. See
[the runtime contract](MT5_T01_DECISION_RUNTIME.md) and
[the major update](RESEARCH_AGENT_MAJOR_UPDATE_2026-10.md).

Remaining: independently verified TradeQuo timestamp semantics, receipt-bound
position observations, submission/protection/recovery orchestration, market-closure
recovery, and separately authorized demo execution acceptance. Complete dashboard
analytics/controls, genuine model-driven campaign acceptance and screenshot
annotations are not claimed complete. T01 remains NOT_DEPLOYED and disabled.

Verified this checkpoint: **2,037 backend passed, 41 skipped**, one existing
Starlette/httpx deprecation warning, in 605.12s. Focused worker/runtime/monitoring:
**47 passed**. Frontend: **144 passed**. Production build passed first attempt,
176 modules, existing chunk warning. Fixture browser smoke passed at
**390/1024/1440/1920px**, including recovery labels, stale/retry, reload, paging,
GET-only requests and no runtime errors/page overflow. Diff check passed.
The new worker suite contributes 12 cases. No real broker or Docker acceptance
was rerun. The bounded-runtime performance probe and its temporary-file cleanup
limitation are recorded in the major update; neither is live execution evidence.

### Paginated diagnostic decision evidence (24 October)

Algo Trading's worker table now opens recorded diagnostic decisions. The bounded
read-only endpoint uses stream/sequence cursor paging, verifies persisted checksums
and returns only allowlisted timestamps, decision type and numeric instructions.
Corrupt evidence remains visible as unavailable; raw observations/provider data
are not returned. No strategy reconstruction, broker request or state mutation
occurs when inspecting history. The UI preserves the previous page on failure,
guards stale responses, and explains that suggestions/no-signal observations are
not broker trades or invented waiting reasons. Filters apply to the loaded page.

No new schema in this increment. Tests cover actual T01 runtime output, unchanged
legacy databases, stream isolation, paging during insertion, sanitized signal
projection, corrupt evidence and API bounds/read-only behavior. Execution and
broader remaining-work limitations above are unchanged.

Final decision-history verification: **2,045 backend passed, 41 skipped**, one
existing Starlette/httpx deprecation warning, in 590.08s. Focused decision history,
monitoring and worker tests: **28 passed**. Frontend: **144 passed**. Production
build passed first attempt (177 modules, existing chunk warning). Fixture browser
smoke passed at **390/1024/1440/1920px**, including decision paging, failed-page
retention/retry, recovery, reload, GET-only requests and no runtime errors or page
overflow. Diff check passed. Eight new backend cases cover the decision view.
No live broker, orders or real-Docker acceptance was performed in this increment.

### Acceptance budget and Windows configuration check (24 October)

The user authorized an initial USD 5 total API test allowance and future demo
trades, then explicitly held paid model calls while Windows backend status is
established. No paid generation or orders were made. The previous verified worker
and decision-history commits were pushed to feature/mt5-demo-execution.

Added a shared persistent pre-dispatch acceptance cap (maximum USD 5), covering
concurrent/in-flight and failed/unknown calls across projects in one database.
It survives restart/removal of the environment setting and has no reset/refund
or increase endpoint. Two additive tables are initialized only on capped use;
production schema/data were not changed. Model requests explicitly use default
service tier. A safe GET model-status endpoint reports config and reservation/
usage estimates without keys, provider calls or table creation.

Windows settings have a key and gpt-6.1-sol selected. A free model-metadata GET
returned HTTP 200; paid generation remains untested. Configured USD 1/5 rates are
Flex/Batch rates; standard calls require current USD 2/10 per million tokens.
The stored secret configuration was not rewritten. No Ledger API was found on
the checked local ports. Read-only DB checks found no active campaigns/loops or
queued/running backtest jobs; two stale BASELINE_RUNNING projects remain intact.
Normal startup performs recovery and scheduling, so the user backend was not
launched merely to check configuration. Details and safe overrides:
[initial acceptance guide](RESEARCH_ACCEPTANCE_BUDGET.md).

The Fedora bridge checker now gathers five advancing tick observations and
summarizes current offset evidence without authorizing conversion or execution.
The user's single sample is consistent with UTC+3 minus 2.359 seconds of quote
age, not a verified seasonal policy. Timestamp/position/protection integration,
real demo acceptance, complete monitoring and screenshots remain outstanding.

Final verification (24 October 2026): backend 2,054 passed, 41 skipped (701.53s); frontend 144 passed; production build passed on unchanged retry after a Windows Rolldown resolution failure. No paid generation calls were made. One read-only model metadata request succeeded. The subsequent campaign-diagnostics investigation is a separate checkpoint.

### Current priority: Research Agent failure diagnostics

See [the 24 October investigation](RESEARCH_DIAGNOSTICS_2026-10-24.md).
The ORB market mismatch and both evidence-reference failures are traced from saved
records/code. The first repair adds early market rejection, schema-bound citations,
persisted sanitized validation details, and a diagnostics panel using existing polling.
The comprehensive lifecycle event stream, authenticated cursor endpoint, private
traceback handling and wider failure coverage remain unfinished. Complete those
before resuming genuine acceptance, MT5 protection/recovery and dashboard work.
No paid retries or automated execution were enabled during this investigation.

First diagnostics repair verified: backend 2,059 passed / 41 skipped (623.82s),
frontend 145 passed, production build passed, mocked browser 390/1024/1440/1920
including diagnostics after reload passed, and diff whitespace check passed.

### 25 October: durable research lifecycle diagnostics

The next checkpoint adds transactional bounded events, a token-authenticated cursor
endpoint, private sanitized exception frames, frontend in-memory authentication,
and independent compatible-family discovery. See
[Research event diagnostics](RESEARCH_EVENT_DIAGNOSTICS.md) for configuration,
exact scope and remaining limitations. No paid calls, broker orders or production
database initialization are part of the automated verification.

### Implemented: dual MT5 accounts and Fedora deployment

User brief read: attachment `facfbeee-a0f8-4ae4-a0d9-9003be651ae8`.
After the Research Agent repair, added LIVE read-only bridge at 127.0.0.1:18766
using `/home/SJH/.mt5-live`; preserve DEMO `/home/SJH/.mt5`, port 18765 and the
separate Telegram bot. Pin environment/login/server before and after operations.
Provide an idempotent guided `deploy/setup-mt5-live-bridge.sh` with --check,
--install and --validate, private independent config/token, account confirmation,
temporary-DB import acceptance, safe profile merge and opt-in startup only after
acceptance. Do not edit production SQLite, restart the backend/bot, overwrite
existing config or send orders. User will run Fedora acceptance locally; no SSH
access was provided. Required final guide: `docs/MT5_DUAL_ACCOUNT_FEDORA.md`.
Keep `feature/mt5-demo-execution`; commits/pushes are authorized.

Implementation and operator instructions: [Dual-account MT5 Fedora deployment](MT5_DUAL_ACCOUNT_FEDORA.md).
The new bridge protocol, pinned saved-profile environment, additive private profile
file, guided installer and isolated Journal acceptance are implemented. No schema
migration. Production Fedora installation/acceptance remains pending the user's run.
No backend, DEMO service or Telegram bot was restarted; no orders or paid calls.
The separate Telegram bot's execution safeguards cannot be verified from this repo.

Final dual-account verification: backend **2,075 passed / 41 skipped** (625.13s),
focused broker/deployment **80 passed**, frontend **145 passed**, production build
passed (180 modules), broker browser fixtures at 1024/1440/1920 and Research Agent
fixtures at 390/1024/1440/1920 passed. A reload readiness race in the browser test
was fixed without application changes. Existing deprecation/chunk-size warnings
remain. Real Fedora acceptance and timestamp-seasonality confirmation remain
external; broader T01 execution/protection, complete monitoring and annotations
are not declared finished by this checkpoint.


Verified lifecycle checkpoint: backend 2,065 passed / 41 skipped (601.86s), frontend 145 passed, production build passed, browser 390/1024/1440/1920 including authenticated-reader fixtures, token non-persistence and reload passed. Existing deprecation/chunk-size warnings remain. No paid calls or production DB changes.

