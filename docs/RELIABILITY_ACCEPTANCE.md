# Reliability acceptance: stages 1-10

Code accepted at `1a09820` (3 October 2026). Stage 9 is the protected-scope gate,
not a feature. Stage 10 closes the reliability acceptance before broker additions.
User strategy drafts/edits are separate working-tree changes and were not included.

## Root causes and corrections

| Problem | Correction |
|---|---|
| Research notes and experiments shared an incompatible repository name | Separate repositories, compatibility alias, real API/container tests |
| Axis tests and browser assertions used obsolete contracts | Updated contracts without relaxing causal/numeric assertions |
| Raw Parquet overwrite could damage the last valid cache | Validated temporary payload, atomic replacement, conservative coverage |
| Background warming held provider coordination for excessive ranges | Durable bounded chunks, foreground priority, pause/resume/cooldowns |
| Parent pools multiplied the nominal worker limit | Shared application-owned simulation reservation budget |
| Polling transferred immutable results/configurations repeatedly | Compact projections, shared requests, idle stopping and legacy fallback |
| Replay navigation discarded local state without a guard | Stay/save/discard, verified local persistence, safe failed resume |
| Generic or raw exception errors obscured causes/exposed details | Allowlisted categories across queued research and synchronous data paths |

## Scope and deterministic evidence

`git diff 4dc3da4..1a09820 -- backend/app/backtesting backend/app/indicators
frontend/src/components/chart` is empty. Frozen Gold, Momentum, ORB/Failed-ORB,
engine fills/sizing/causality, indicator rules and drawing implementation were not
changed by these stages. Service changes admit simulations, preserve/cache input
bars, project status, and classify failures; they do not tune strategy parameters.
No AMN, GPU, cloud access or new navigation was added. User-owned strategy edits
remain untouched, so a whole-working-tree diff naturally includes unrelated work.
No credentials or live data were read, no installed dependencies were changed,
and the running Ledger/research process was not restarted.

## Tests and build

| Gate | Evidence |
|---|---|
| Audited backend baseline | 589 passed / 20 failed |
| Final Stage 8 full backend | 737 passed / 0 failed, 92.35s |
| Frontend | 88 passed / 0 failed |
| Production build | Passed, 124 modules; existing large-chunk warning |
| Focused Stage 9-10 acceptance on the same code | 99 passed, 25.64s |
| Whitespace | Changed source/doc checks pass |

Full verification command: `powershell -ExecutionPolicy Bypass -File ./Verify-Ledger.ps1`.
Final artifacts: `C:/Users/jamie/Project/stage8-final` outside the repository.
Existing Starlette TestClient deprecation warning remains. The focused acceptance
covered `test_market_cache_recovery`, `test_market_warmup`, `test_simulation_budget`,
`test_parent_research`, `test_research_items_api`, `test_research_infrastructure`
and `test_release_replay`. No tests were deleted to obtain green results.

The suites exercise interruption before publication, invalid/missing cache repair,
coverage disagreement, previous-payload preservation, provider-call counts, restart
reconstruction of NQ from dated contracts, foreground-before-background scheduling,
concurrent research/global admission, cancellation/release, immutable cells and
research notes CRUD. The full suite additionally covers broker reconciliation,
Journal migration/attachments/identity, Replay, fills and frozen baselines.

Isolated mocked browser checks passed research spectra/grids/run opening and Replay
checkpoint/leave/errors at 1024/1440/1920 with no runtime errors or page overflow.
They do not establish real provider availability. See [verification](VERIFICATION.md)
for retained manual checks; no claim that every older opt-in browser script was rerun.

## Existing 5x5 benchmark

The Stage 5 measurement used five sessions / 1,950 synthetic minute bars and four
workers: **82.867s before**, **80.363s after**, zero provider calls in both runs.
**25/25 exact hashes match** for trades, metrics, setups, analysis and equity curves.
The [recorded JSON](GLOBAL_BUDGET_BENCHMARK.json) is the evidence; this is not a new
measurement at Stage 10 or a statistically established speedup. Subsequent exact
research parity regression tests remain green.

## Operational limitations and deliberate deferrals

- CPU budget is per application process; reserved pool slots are not measured CPU
  utilization, and idle slots inside a pool are not dynamically loaned.
- In-flight HTTP requests cannot be preempted; priority applies between acquisitions.
- Durable NQ reuse requires valid stored evidence. Real Massive entitlement/cooldown
  and TradingView parity were not verified with live credentials.
- SQLite still scans JSON for compact diagnostics; reduced response size does not
  mean zero database work.
- Replay has one browser-local checkpoint, not durable server sessions/crash recovery.
- No universal security audit is claimed. Workspace is trusted local Python.
- Documentation/tests cleanup and TradeLocker/MT5/canonical broker integration are
  separately tracked stages. No live order execution is authorised or implemented.

## Exact committed files for stages 1-8

Generated files, live data and user strategy drafts are excluded. A = new, M = modified,
D = deleted; rename records show both paths. This list is the checkpoint-to-accepted-code
Git diff, not a list of all dirty user files.

```text
M	README.md
A	Verify-Ledger.ps1
M	backend/app/api/data.py
M	backend/app/api/research.py
A	backend/app/api/safe_errors.py
M	backend/app/api/strategy_lab.py
A	backend/app/core/safe_errors.py
M	backend/app/data/providers/massive_futures.py
M	backend/app/research_runtime.py
M	backend/app/services/backtest.py
M	backend/app/services/backtest_jobs.py
M	backend/app/services/container.py
A	backend/app/services/market_coordination.py
M	backend/app/services/market_data.py
M	backend/app/services/market_warmup.py
M	backend/app/services/research.py
M	backend/app/services/research_runner.py
A	backend/app/services/research_status.py
A	backend/app/services/simulation_budget.py
M	backend/app/storage/market_store.py
A	backend/app/storage/market_warmup_repository.py
A	backend/app/storage/research_experiment_repository.py
A	backend/app/storage/research_item_repository.py
M	backend/app/storage/research_repository.py
M	backend/tests/conftest.py
A	backend/tests/test_market_cache_recovery.py
M	backend/tests/test_market_data_service.py
A	backend/tests/test_market_warmup.py
M	backend/tests/test_parent_research.py
M	backend/tests/test_phase63_journal_research.py
M	backend/tests/test_research_futures.py
M	backend/tests/test_research_infrastructure.py
A	backend/tests/test_research_items_api.py
A	backend/tests/test_research_status.py
A	backend/tests/test_safe_api_errors.py
A	backend/tests/test_safe_errors.py
A	backend/tests/test_simulation_budget.py
M	backend/tools/benchmark_parent_research.py
A	docs/GLOBAL_BUDGET_BENCHMARK.json
A	docs/MARKET_CACHE_WARMING.md
A	docs/RELIABILITY_IMPLEMENTATION_STATUS.md
M	docs/RESEARCH_EXPERIMENTS.md
A	docs/VERIFICATION.md
M	frontend/src/api/client.js
M	frontend/src/app/App.jsx
A	frontend/src/app/ReplayLeaveGuard.jsx
M	frontend/src/app/preferences.js
A	frontend/src/features/settings/CacheWarmPanel.jsx
M	frontend/src/features/settings/SettingsPage.jsx
A	frontend/src/features/settings/warmupView.js
M	frontend/src/features/strategy-lab/BacktestJobPanel.jsx
M	frontend/src/features/strategy-lab/ComputeControl.jsx
M	frontend/src/features/strategy-lab/ReplayPanel.jsx
M	frontend/src/features/strategy-lab/ResearchExperimentViewer.jsx
M	frontend/src/features/strategy-lab/ResearchHistory.jsx
A	frontend/src/features/strategy-lab/replayCheckpoint.js
M	frontend/src/features/strategy-lab/researchExperiments.js
A	frontend/src/features/strategy-lab/researchPolling.js
A	frontend/src/features/strategy-lab/statusPolling.js
M	frontend/src/features/strategy-lab/useBacktestJobs.js
A	frontend/tests/browser/market-warmup.mjs
A	frontend/tests/browser/replay-leave-guard.mjs
M	frontend/tests/browser/research-experiments.mjs
A	frontend/tests/market-warmup.test.js
A	frontend/tests/replay-checkpoint.test.js
A	frontend/tests/status-polling.test.js
A	frontend/verify-build.mjs
```
