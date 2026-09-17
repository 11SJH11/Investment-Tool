# Checkpoint 7 — regression and current-documentation handoff

2026-09-17. Checkpoint 6 implementation is commit `1212044`; checkpoint 5 was
`ff93317`. This checkpoint changes documentation only. It is not the final
release acceptance report: the newly authorized checkpoint 8 is still pending.

## Verification against the checkpoint 6 implementation

From backend, using `.venv/Scripts/python.exe`, fresh temporary basetemp directories
and `-p no:cacheprovider`:

- Full `-m pytest -q`: **408 passed**, 50.56s; two pre-existing dependency
  deprecations (Starlette/httpx and AnyIO BlockingPortal).
- Focused regression command: **327 passed**, 45.31s, the same two warnings:

```powershell
.venv/Scripts/python.exe -m pytest -q tests/test_release_replay.py tests/test_release_journal.py tests/test_phase6_journal_report.py tests/test_phase63_journal_research.py tests/test_phase5_engine.py tests/test_phase56_replay_workspace.py tests/test_phase561_replay_consistency.py tests/test_phase55_research_and_replay.py tests/test_phase4_journal.py tests/test_oanda_journal_import.py tests/test_momentum_vcp_baseline.py tests/test_journal_v2.py tests/test_journal_diagnostics.py tests/test_intraday_baselines.py tests/test_gold_experiments.py tests/test_futures_foundation.py tests/test_broker_sync.py tests/test_broker_connections.py tests/test_strategy_workspace.py -p no:cacheprovider --basetemp "$env:TEMP/ledger-cp7-focused-$([guid]::NewGuid().ToString('N'))"
```

This covers Replay causality, Journal/preservation, broker profiles and Trading
212, OANDA history/import identity, futures economics, trusted Workspace,
Momentum/VCP, frozen Gold, Gold experiments, ORB/VWAP and the engine. Gold's
experimental reference also has a hand-worked exact trade-equivalence assertion.

From frontend:

- `node --test tests/*.test.js`: **17 passed**, zero failures, 189ms.
- `npm.cmd run build -- --outDir "$env:TEMP/ledger-cp7-build-final"`:
  **passed**, 70 modules, 1.57s. Existing >500kB chunk warning remains.
- `git diff --check`: passed.

## Isolated browser checks

Headless Chrome at 1024 x 900, current production bundle, temporary databases,
synthetic market/broker fixtures. External HTTP blocked; only MockTransport
broker requests allowed. No real broker keys/accounts or user data used.

- OANDA Journal sync creates one canonical trade; second sync creates zero and
  refreshes the existing trade. Journal table and Analysis render correctly.
- Trading 212 sync imports five fixture records; duplicate sync creates zero.
  Current broker Portfolio renders. Investor-friendly metrics remain checkpoint 8B.
- Workspace checks syntax and saves in an isolated strategy directory without
  executing the saved source. Broader execution/protection tests pass in pytest;
  checkpoint 4's historical browser execution checks are not claimed as rerun.
- Replay NQU6 5m -> 15m -> 1m preserves frontier Visible 33/90. One whole-contract
  entry, queued manual exit and a switch back to 5m produce exactly one Journal
  record: 0.25 points x USD20 = USD5. No reset or duplicate write.
- Fresh ORB and VWAP runs through the UI produce saved results and Trade Audit
  metadata. Gold comparison selects all 12 fixture identities and shows retention,
  missing DXY diagnostics, sample counts and date breakdowns.
- No observed application runtime exception or page-level horizontal overflow
  in these checks. Initial smoke harness waits needed lowercase display text and
  strategy-registry load completion; corrected scripts passed without app changes.

Temporary evidence/helpers: `%TEMP%/ledger-cp7-smoke-0geop6yv/`, including
`broker-portfolio.png` and `replay-futures.png`; checkpoint 6 comparison screenshot
is under `%TEMP%/ledger-cp6-smoke-o0ht6_w2/`. Test servers and browsers were stopped.
These tests validate deterministic integration, not live provider coverage.

## Documentation changes

Changed: `docs/ARCHITECTURE.md`, `docs/DATA_SOURCES.md`,
`docs/PRODUCT_ROADMAP.md`, `docs/STRATEGY_LAB.md`, `docs/RELEASE_CHECKPOINTS.md`.
Added: `docs/RELEASE_CHECKPOINT_7.md`.

Current docs now describe Journal V2, automatic Replay imports, broker profiles,
separate Trading 212 snapshots, futures economics, continuous chart provenance,
Workspace and current strategies/comparison. Market vs persistent limit entries
are distinguished. Historical checkpoint-specific reports remain intact.
No code, schema, migrations, credentials, databases or frozen rules change here.

## Next continuation: checkpoint 8

Read the current continuation brief in the user attachment
`cc987580-538f-4988-81cd-238f1ccdeecf/pasted-text.txt` before implementing.
The user explicitly authorized the previously deferred continuous-futures work;
do not ask again based on the older AGENTS.md deferral.

Required: current official TradingView-methodology research; generic versioned
roll schedules; raw vs adjusted distinction; NQ1! Backtest/Replay resolving dated
contracts; cross-roll safeguards; provenance through aggregation/cache/Journal;
parity-validation workflow without fabricated TradingView evidence; durable
Massive contract reference cache with single-flight, safe 429 fallback and bounded
retry; targeted Trading 212 position/account metrics; broker-adapter extension
audit/documentation/tests. Then the full checkpoint 8 verification and final report.

Current limitations remain: continuous execution is blocked, calendar-front roll
is not TradingView-equivalent, Massive reference discovery lacks durable caching,
and Portfolio snapshot presentation still needs the requested corrections.
DXY-dependent Gold variants have no verified data path. No claim of complete
release acceptance, point-in-time stock universes or live provider parity is made.
