# Strategy Workspace — Checkpoint 4

Open **Backtest → Strategy Workspace**. The local editor supports a new template,
loading existing strategy source, syntax highlighting, editable copies, static
syntax checking, saving, interface validation, deterministic test functions and
backtesting through the common Ledger service/engine.

## File and execution contract

- Workspace filenames are `_workspace_name.py`, stored in
  `backend/app/backtesting/strategies/`. The strategy key must be `workspace_name`.
- Workspace files use the underscore prefix already excluded by plugin startup
  discovery. Saving does not activate/import them, including after restart.
  They are listed separately in Workspace, not in the ordinary built-in registry.
- All built-ins, including frozen Gold and Momentum, are read-only. Use **Make
  editable copy**, choose a workspace filename and change its StrategySpec key.
  Workspace has no built-in overwrite endpoint or automatic activation step.
- Saves validate Python syntax, compare the expected source revision and replace
  the file atomically. Existing files cannot be overwritten with a missing/stale
  revision. Paths, traversal, alternate streams and symlink files are rejected.
- Reading, pasting, highlighting, saving and syntax checks do not execute draft
  code. Syntax checking uses AST parsing. Invalid drafts remain in the editor;
  invalid syntax cannot replace a saved file. Maximum source size is 100 KB.
- Interface validation, tests and backtests require a checked trusted-code
  acknowledgement **and** an explicit execution button/API action. They can run
  the current unsaved draft, whose hash identifies the code actually used.
- Each execution uses a fresh Python subprocess. Validation/tests have a 15-second
  timeout; backtests have 120 seconds. Workers use a temporary working directory
  and do not receive inherited application credential environment variables.
  Backtests receive configured settings over a private stdin pipe so the existing
  provider routing/cache path can work; credentials never enter command arguments.
- stdout/stderr are captured with bounded memory, but raw output and exception
  text are withheld. UI reports output counts, exception type and draft line where
  available. Configured secret values, including broker-profile secrets, are
  redacted from structured results and saved run settings/notes.
- Workspace endpoints require a local client and reject non-local browser
  origins. This is **trusted local Python execution, not a secure sandbox**.
  Executed Python still has the user's filesystem/network privileges. Timeouts,
  redaction and read-only built-in endpoints do not confine hostile Python or
  guarantee that arbitrarily encoded secrets cannot escape. Do not expose this
  feature through a public reverse proxy. Do not put secrets in strategy source.

## Plugin and test interface

One Strategy subclass per workspace file, with a StrategySpec, supported
timeframes, a synchronous `on_bar(self, ctx)` override and default construction.
The normal registration decorator is supported; the worker can register the
single class if the decorator is omitted. Frozen/built-in keys cannot be replaced.
Unexpected extra registrations fail validation. Module top-level code executes
on explicit interface/test/backtest actions, just like importing a Python plugin.

The default template is intentionally a no-trade skeleton, not a strategy with
claimed performance. It includes one simple `test_strategy()` example.

**Run strategy tests** invokes synchronous, zero-argument `test_` functions defined
in that file. Write assertions with hand-worked synthetic fixtures. Each function
gets a pass/fail result. No test functions is reported as a failure, not a green
zero-test run. This runner does not implement pytest fixtures, parametrization or
async tests. Tests can import Ledger's engine/context to exercise strategy behaviour.
Interface validity does not establish correctness, causality or profitability.

## Backtests and saved results

Edit the JSON settings in the Workspace panel: symbols, dates, timeframe, strategy
parameters, balance, risk sizing, costs, schedule and other normal BacktestRequest
fields. The server derives the strategy key from the filename. **Run workspace
backtest** uses BacktestService, MarketDataService and BacktestEngine unchanged.
It applies the same equity/OANDA/futures restrictions, fills and accounting.

Successful runs save through the existing BacktestRunRepository and appear in
**Runs**. Open them for normal performance tables and Trade Audit. Snapshots record
the workspace filename and SHA-256 of the executed source, alongside normal run
configuration/results. Source itself is not embedded in saved runs: preserve exact
source versions yourself if you need to reproduce old results. Changed files do
not silently recalculate existing snapshots. **Use settings** for a workspace run
directs the user back to Workspace and shows the recorded source hash; it does not
activate user code in the built-in registry or silently run a changed file.

Draft state survives Backtest/Workspace/Runs tab changes. Leaving Backtest with
unsaved edits prompts before discarding them, as does replacing the editor content.
Browser close/reload also warns. Drafts are not automatically written to storage;
save before a restart. Leaving during an execution does not cancel its backend job.
The editor provides basic Python token highlighting and Tab indentation, not an
IDE debugger, autocomplete server or package installer. Modules using relative
package imports need adjustment for the standalone draft module.

## Storage and exact files

No schema migration, database replacement or user-data rewrite. New user strategy
files are normal UTF-8 source. Existing backtest JSON snapshots hold the additional
workspace provenance. Tests and smoke checks used temporary files/databases only.
No user credentials, existing strategy source, engine, Replay, Journal, charts,
market-data routing or strategy rules were changed for this checkpoint.

Changed:

- `backend/app/api/router.py`
- `frontend/src/api/client.js`
- `frontend/src/app/App.jsx`
- `frontend/src/features/strategy-lab/StrategyLabPage.jsx`
- `docs/RELEASE_CHECKPOINTS.md`

New:

- `backend/app/api/strategy_workspace.py`
- `backend/app/backtesting/workspace_worker.py`
- `backend/app/services/strategy_workspace.py`
- `backend/tests/test_strategy_workspace.py`
- `frontend/src/features/strategy-lab/StrategyWorkspace.jsx`
- `frontend/src/features/strategy-lab/workspace-utils.js`
- `frontend/tests/workspace.test.js`
- `docs/STRATEGY_WORKSPACE.md`

## Verification

Commands use the backend virtualenv, temporary pytest basetemp directories and
`-p no:cacheprovider`. Frontend output is outside the source tree.

- `pytest -q tests/test_strategy_workspace.py`: **27 passed**, 2 existing
  deprecation warnings, 13.77 seconds. Covers static non-execution, real startup
  discovery exclusion, filenames/built-in protection, optimistic saves, syntax,
  explicit acknowledgement, interface errors, test outcomes, timeout, captured
  output, secret redaction, local-origin restrictions and a real subprocess
  backtest from cached synthetic data with saved results.
- Full backend `pytest -q`: **320 passed**, 2 existing deprecation warnings,
  40.78 seconds.
  Includes all prior Journal, broker, migrations, engine, Replay, futures, frozen
  XAU and Momentum tests.
- `node --test tests/*.test.js`: **12 passed**, including 2 new highlighting
  tests and all 10 previous Journal/futures utility tests.
- `npm.cmd run build -- --outDir <unique-temp>`: **passed**, 68 modules,
  1.63 seconds. Existing large-chunk warning remains.
- `git diff --check`: passed.
- Isolated headless Chrome at 1024px: syntax-error line, syntax-highlighted editor,
  nonexecuting save, trusted acknowledgement, interface validation, test execution,
  workspace backtest and saved-run provenance, tab persistence, read-only frozen
  source and disabled save, unsaved-navigation cancellation, no page overflow and
  no observed runtime exceptions during completed checks. Synthetic backtest used
  default 1% risk: 100 shares, $100 risk, $200 profit, 2R. An initial smoke assertion
  incorrectly expected one-share P&L; it was corrected to the actual configured
  sizing. This was a harness correction, not a strategy or engine change.
- Screenshot/scripts remain under temporary `ledger-cp4-smoke-niqvdql6`.
  Provider endpoints pointed to a closed loopback port and complete synthetic cache
  coverage supplied the backtest. No real broker/provider calls were made.

## Manual acceptance

1. Open Workspace. Paste invalid Python; Check syntax should report a line and
   leave the draft editable. Fix it and save as `_workspace_example.py` with key
   `workspace_example`. Load it again and compare source.
2. Confirm execution buttons are disabled until trusted-code acknowledgement.
   Validate the interface; add deterministic `test_` assertions and run them.
   Check failing assertions and an intentional loop timeout in disposable code.
3. Load frozen Gold or Momentum source. It must be read-only; making a copy must
   not change the original. Attempting a built-in filename through the API must fail.
4. Configure a small backtest with entitled/cached data and explicit costs. Run it,
   open its saved result, inspect trades/Trade Audit, and retain the source version
   matching the recorded SHA-256. Futures must still use supported dated contracts.
5. Edit a draft, switch Runs/Workspace, then try leaving Backtest. Confirm the draft
   survives tab switching and cancelling the discard prompt keeps it open.

Checkpoint 5 (ORB/VWAP), 6 (Gold variants/comparison), and 7 (release-wide final
verification/report) are still pending. Checkpoint 4 does not implement them.
