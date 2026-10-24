# T01 completed-bar decision diagnostics

This is an internal, execution-disabled decision runtime. It is not a running
T01 deployment, order gateway, broker position manager or public activation API.
No ordinary Ledger startup, profile connection or bridge sync starts it.

## What is implemented

`backend/app/forward/mt5_t01_runtime.py` uses the registered
`gold_ifvg_v2_skip_23et` implementation, canonical `StrategyContext` and Market
Concepts. It does not copy or modify the strategy's entry/management rules.

Preparation requires an existing demo execution policy, matching registered
strategy source hash, approved symbol and explicit `verified_utc` input contract.
Preparation archives loaded strategy source as data and records implementation,
runtime, dependency and immutable definition hashes. Existing source archives
are never executed. The source archive retains its existing limited scope;
this is not a complete portable Python environment.

Each stream starts at 20:00 America/New_York and consumes continuous completed
one-minute bars. Fifteen-minute candles require all 15 constituent minutes.
Future, incomplete, changed, missing and out-of-order bars fail closed. There is
no fixed broker UTC offset or inferred holiday/session calendar. Streams are
bounded to 2,880 bars; they do not automatically bridge market closures.

Decisions preserve the frozen first-setup/session state, exclusion of first
setups confirmed at 23:00 ET, 1R target instruction and +0.68R breakeven instruction.
The decision and earliest eligible application time are saved; there is no
simulated fill or broker order. In particular, an entry signal without a broker
position observation is not treated as an executed trade.

Caller-supplied position observations require explicit attribution, the selected
symbol, T01 strategy metadata and an entry time no later than the completed bar's
start. This assertion is an **internal integration contract**, not implemented
broker attribution. The future coordinator must construct it from independently
verified receipts/reconciliation. No HTTP endpoint accepts these observations.

Restart reconstructs strategy state by replaying the persisted bar and position
observations and comparing decisions. Source/runtime drift or replay mismatch
halts the diagnostic stream. Transactions atomically store the decision and
advance its revision; concurrent writers cannot both advance the same frontier.
Failures clear cached state so retries rebuild from the last committed evidence.
Repeated identical latest observations do not create duplicate decisions.

## Storage and monitoring

The internal runtime initializes two additive tables on construction:

- `mt5_t01_diagnostics`: immutable definition/hash and committed revision.
- `mt5_t01_decisions`: bar, observation, decision, timestamps and integrity hash,
  keyed by stream and sequence.

No existing Journal, execution attempt, account guard or policy state is changed.
Normal application construction now initializes this additive schema and the
worker table described below. Development verification used temporary databases,
not the user's running database.

Algo Trading preparation details can display the newest prepared diagnostic
stream's saved count, decision timestamp and signal kind. They do not show it as
Running, a current account position, a trade or a worker heartbeat. The persisted
policy and execution-disabled labels remain unchanged.

## Verification

From `backend`, with the normal development environment:

```powershell
.venv/Scripts/python.exe -m pytest -q tests/test_mt5_t01_runtime.py
```

Tests use isolated temporary databases and synthetic market data. They exercise
Sunday and both New York seasonal offsets, completed confirmation, management,
restart, idempotency, missing/future/revised data, source/definition drift, failed
database writes, concurrent writers, the 23:00 exclusion, limits and monitoring.
No credentials, terminal or orders are involved.

Full checkpoint counts and build/browser results are in
[the current handoff](UNIFIED_DEVELOPMENT_2026-10.md).

## Read-only MT5 observation cycle

`mt5_t01_feed.py` and `mt5_t01_poll.py` now connect one explicit diagnostic cycle
to the existing broker profile locks and native/bridge adapter. A manually started
diagnostic worker can repeat the cycle; there is no startup activation or new
public endpoint.

The cycle requires an enabled DEMO profile, its selected opaque account identity,
an explicit terminal path or bridge, and matching currency. The collector passes
only terminal/bridge connection settings; it never passes login/password/server
options that could switch a native terminal account. Adapter shutdown releases
Python IPC, not the MT5 terminal. Existing profile and process-global adapter
locks protect the read lifecycle.

Only the latest fully completed minute is eligible. A fresh UTC quote, exact
broker symbol, connected terminal and unchanged demo identity are required. The
immediately preceding persisted minute is re-read and compared before advancing.
Missing/revised/duplicate/future rows fail; a native range's forming right-edge
bar is excluded. Volume is explicitly MT5 tick volume, not shares/contracts.
The profile, timestamp policy, volume basis and observation basis are recorded
with the decision. Source fingerprints include the feed/poll implementation.

The account must have no open positions or pending orders both before and after
collection. This deliberately conservative diagnostic boundary does not attribute
manual trades or substitute a flat position for unknown broker state. It is not
an atomic broker snapshot or permission to trade; broker state can change between
reads. A separate receipt-bound position mapper is still required.

Repeated polling within an already committed minute does not contact MT5.
Missed minutes/clock rollback require explicit recovery; no historical orders or
automatic backfill are generated. Cancellation before collection or after the
read leaves the frontier intact. Provider failures retain existing decisions and
release locks. The five-second observation budget is checked after native reads;
it does not forcibly interrupt a blocked native call. Bridge watchdog/transport
timeouts retain their existing behavior.

This path cannot infer the TradeQuo seasonal rule. `verified_utc` remains an
independently established input contract, and +2/+3-hour quotes are rejected
rather than shifted. An unverified bridge timestamp policy also blocks reads.
Research Agent contexts cannot invoke this diagnostic feed.

Focused isolated verification:

```powershell
.venv/Scripts/python.exe -m pytest -q tests/test_mt5_t01_feed.py tests/test_mt5_t01_poll.py tests/test_mt5_t01_runtime.py
```

## Persistent diagnostic worker

`mt5_t01_worker.py` owns explicit internal `start`/`stop` operations and bounded
shutdown. Constructing Ledger does not start a worker or contact MT5. A first
stream waits until 20:01 America/New_York to observe the completed 20:00 bar;
it does not backfill a missed opening decision. Subsequent missing minutes fail
closed. This is not market-closure recovery or an indefinite deployment.

The additive `mt5_t01_workers` table stores stream/profile/account identity,
process owner, lease generation, state, heartbeat, last cycle/decision and safe
error category. A partial unique index allows only one active stream per account.
Fresh ownership cannot be reclaimed. Explicit recovery of a stale same-stream
owner increments the generation; a different active stream must be resolved first.
Commit guards validate ownership and cancellation inside the decision transaction.
Late native replies cannot advance a stopped or superseded worker's frontier.

Monitoring reports actual local thread liveness separately from persisted state.
Missing threads require recovery; stale or future heartbeats are not healthy.
Restart never resumes trading or diagnostics automatically. A blocked native call
may outlive the two-second shutdown join budget, remains visibly STOPPING, and
cannot commit after shutdown. Native-call interruption is not guaranteed.

Algo Trading shows these states in a read-only table. Diagnostic workers are not
trading deployments, have no order authority and do not manage existing positions.
There is no public start/stop endpoint in this increment. Internal verification:

```powershell
.venv/Scripts/python.exe -m pytest -q tests/test_mt5_t01_worker.py tests/test_mt5_t01_poll.py tests/test_mt5_t01_runtime.py
```

### Inspecting recorded decisions

In Algo Trading, choose **View decisions** on a diagnostic worker. The table
shows recorded no-signal, entry, management and exit decisions, their timestamps,
eligible application time and suggested stop/target instructions. These are not
orders, trades, broker protection or a claim that a signal was executed. The
runtime does not record a specific reason for every no-signal evaluation.

`GET /algo-trading/diagnostic-decisions?stream_id=<64-character stream ID>` reads
up to 50 records by default (maximum 100). `before=<sequence>` pages backwards;
new writes do not shift earlier pages. The composite stream/sequence primary key
supports bounded reads. Filtering in the UI applies to the loaded page, not the
entire stream. Failed page requests retain the previous page with a visible error.

This endpoint neither reconstructs strategy state nor contacts MT5. It validates
stored checksums, exposes allowlisted scalar fields, and displays invalid evidence
as unavailable without returning its contents. A checksum verifies stored content
consistency, not broker authenticity. Raw observations, position metadata and
source archives are excluded. It has no mutation/control route or schema migration.

## Still required before a real T01 deployment

1. Independently validate MT5 timestamp representation and feed continuity. The
   `verified_utc` argument does not perform that verification.
2. Extend the diagnostic worker into the separately authorized deployment
   lifecycle, with market-closure recovery and position-management pause semantics.
3. Build broker-attributed position observations and atomically connect decisions
   to risk checks, intents, receipts, protective orders and recovery. Diagnostic
   records are never submission authorization.
4. Measure replay/history performance at the stream bound. Current replay is
   bounded and deterministic, but a 48-hour production latency target is not yet
   established; this is not an indefinite-history worker.
5. Obtain separate explicit authorization for demo orders and perform genuine
   protection/reconnect/recovery acceptance. Live accounts remain excluded.
