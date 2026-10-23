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

The internal runtime initializes two additive tables on explicit construction:

- `mt5_t01_diagnostics`: immutable definition/hash and committed revision.
- `mt5_t01_decisions`: bar, observation, decision, timestamps and integrity hash,
  keyed by stream and sequence.

No existing Journal, execution attempt, account guard or policy state is changed.
This checkpoint does not initialize these tables in the user's running database.

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

## Still required before a real T01 deployment

1. Independently validate MT5 timestamp representation and feed continuity. The
   `verified_utc` argument does not perform that verification.
2. Implement the persistent polling worker, deployment lifecycle/heartbeat,
   recovery at market closures, and pause/stop semantics.
3. Build broker-attributed position observations and atomically connect decisions
   to risk checks, intents, receipts, protective orders and recovery. Diagnostic
   records are never submission authorization.
4. Measure replay/history performance at the stream bound. Current replay is
   bounded and deterministic, but a 48-hour production latency target is not yet
   established; this is not an indefinite-history worker.
5. Obtain separate explicit authorization for demo orders and perform genuine
   protection/reconnect/recovery acceptance. Live accounts remain excluded.
