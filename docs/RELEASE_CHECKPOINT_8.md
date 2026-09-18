# Checkpoint 8: continuous execution handoff

2026-09-18. Builds on `b9bd4d7` (cache, investor Portfolio and broker audit).
Implementation is verified with synthetic data. **TradingView parity and live
provider coverage are unverified**; no licensed comparison exports were supplied.

## Methodology and execution

Default schedule: `prior-session-volume45-v1`, generic across the twelve registered
families. Adjacent contracts are ordered by provider last-trade date. In the 45
calendar days before the front expiry, compare matching session-date volumes.
The first strictly greater next-contract volume qualifies. Missing sessions are
not zero; ties do not qualify. A session is conservatively complete at the later
of its start + 24 hours and 18:00 New York on its provider session-end date.
Switch at the first subsequent observed next-contract session start at/after that
boundary. That new session's OHLCV does not participate in the decision. Do not
switch back. No observed crossover uses `expiry-fallback` at UTC midnight after
the provider last-trade date. Nonchronological transitions are rejected instead
of overlapping two source contracts.

This volume-window rule and expiry fallback are **Ledger approximations**. They
are not TradingView's undisclosed per-symbol historical switching rule. In
particular, adjacent listed monthly commodity contracts are not necessarily the
same active-month sequence used by another vendor. There is no settlement-time,
delivery, first-notice or broker-margin model. Exact root-specific alignment is
a future evidence-driven refinement, with a new schedule version when rules change.

Reference/schedule records share the durable metadata database under distinct
versioned keys. Pair keys include contract reference dates; developing schedules
use an hourly key, historical pairs use a final key. Existing cache TTL/cooldown
and process-wide single flight apply. Explicit refresh updates schedule evidence.
Provider daily evidence is fetched once per cached pair, independent of displayed
timeframe. There can be two daily aggregate requests per uncached pair; these are
separate from the already cached contract-discovery request.

Raw dated OHLCV remains in the shared MarketDataService cache. Continuous history
is reconstructed against the schedule on retrieval, rather than persisting stale
alias bars selected before delayed roll evidence became available. A regression
covers evidence changing from expiry fallback to an earlier observed crossover.
Existing caches are retained; provenance-v3 uses a separate namespace.

Each continuous bar retains alias, source contract, schedule version, provider,
adjustment mode/method/offset, effective roll time and last-trade date. Aggregation
groups by source contract, so a bar cannot blend two contracts. Chart/Replay
disclosures show the current contract and revealed/loaded transition list without
altering chart drawing infrastructure.

`FUTURES_BACK_ADJUST=false` remains the default. Adjusted charts add cumulative
new-close minus old-close differences to older segments, using the latest common
completed daily session at/before each actual switch. Missing common closes reject
adjustment; adjacent intraday price gaps are not substituted. Older prices depend
on later rolls in the requested range, so adjusted data is chart context, not
causal execution data. Raw execution uses a provider copy and a separate raw cache;
the shared chart setting is never mutated.

Backtest/Replay front aliases resolve raw same-family dated contracts from valid
bar provenance. No provenance, adjusted prices or wrong-family sources fail
explicitly. Tick size, USD point value, full-notional constraints and whole-contract
sizing use the existing generic economics. Strategy rules/fills/cost policies are
unchanged. A $10,000 account does not gain invented NQ margin leverage.

An open position reaching a different source contract rejects the Backtest run
before marking or filling against the new contract. Replay terminates before a
cross-roll fill, retains the last processed frontier, marks integrity compromised
and requires a fresh session. Pending entries cancel at a roll. Flat sessions can
continue. Journal stores displayed_symbol and executed_contract in source_metadata
and calculates P&L using the dated multiplier; existing IDs/notes remain intact.

## TradingView comparison

Official references and exact differences are in CONTINUOUS_FUTURES_RESEARCH.md.
The offline tool `backend/tools/compare_continuous.py` compares timestamp-matched
OHLCV, missing bars, optional source IDs and transition lists. Use separate 1m,
5m, 15m and 1h exports covering five trading days either side of several actual
NQ roll markers. Keep session, timezone, price adjustment and feed entitlement
matched. Do not fill missing data or shift prices to manufacture agreement.
Real exports were not available: no measured vendor discrepancies or equivalence
are claimed. Daily-close adjustment follows the documented concept, but identical
roll timestamps/data/close selection have not been demonstrated.

## Exact files in this continuation

Changed:

- backend/app/backtesting/engine.py
- backend/app/backtesting/strategies/intraday_baselines.py (instrument resolution only)
- backend/app/data/futures.py
- backend/app/data/instruments.py
- backend/app/data/providers/massive_futures.py
- backend/app/services/backtest.py
- backend/app/services/journal.py
- backend/app/services/market_data.py
- backend/tests/test_futures_foundation.py (front execution capability; explicit legacy policy)
- backend/tests/test_phase62_multi_asset.py (explicit legacy calendar policy)
- frontend/src/features/charts/ChartsPage.jsx
- frontend/src/features/strategy-lab/ReplayPanel.jsx
- frontend/src/features/strategy-lab/futures-utils.js
- frontend/tests/futures.test.js
- docs/ARCHITECTURE.md
- docs/CONTINUOUS_FUTURES_RESEARCH.md
- docs/DATA_SOURCES.md
- docs/PRODUCT_ROADMAP.md
- docs/STRATEGY_LAB.md
- docs/RELEASE_CHECKPOINTS.md

Added:

- backend/app/data/continuous_schedule.py
- backend/app/data/continuous_comparison.py
- backend/tests/test_continuous_execution.py
- backend/tools/compare_continuous.py
- frontend/src/components/FuturesProvenance.jsx
- docs/RELEASE_CHECKPOINT_8.md

No application database migration. Schedule payloads use the metadata cache table
introduced in part 1; Journal identities use existing JSON metadata. No real user
database, broker credentials or orders were used. Gold baseline/variants and
Momentum rules are unchanged; Gold formulas remain in GOLD_EXPERIMENTS.md.
The part-1 report contains the exact earlier cache/Portfolio files, available
investor metrics and limitations. BROKER_EXTENSION_CONTRACT.md describes the
shared Journal contract and remaining provider-registration coupling.

## Verification and manual acceptance

Full backend: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider
--basetemp <unique temporary directory>`: **454 passed**, 55.98s, two existing
dependency deprecations. Focused: **373 passed**, 50.09s, same two warnings;
the part-1 focused command plus `tests/test_continuous_execution.py` covers the
same named suites and all new continuous execution/roll cases. `git diff --check`
passed. Frozen Gold and Momentum implementations were not modified.
New continuous suite: **26 passed**, 3.86s. Frontend:
`node --test tests/*.test.js`: **22 passed**. Production build:
`npm.cmd run build -- --outDir "$env:TEMP/ledger-cp8-execution-build"` passed,
72 modules, 7.78s; final repeat to `ledger-cp8-verified-build` passed in 1.45s,
with identical asset hashes. Existing large-bundle warning remains.

Isolated final frontend build in headless Chrome, 1024×900, temporary application
data/strategies and synthetic providers; external HTTP blocked:

- NQ1! Replay 5m → 15m → 1m preserves canonical frontier; entry and queued close
  across timeframe change produce one Journal trade, NQ1!/NQU6, one contract,
  0.25 points = $5. Revealed source and schedule disclosure render.
- NQ1! ORB submitted through the normal form, immutable saved result and Trade
  Audit opened. Chart NQ1! raw/source/schedule disclosure renders.
- Twelve saved Gold variants compare with baseline retention metrics.
- Trading 212 useful holdings, currency separation, notes/resync, hidden empty
  manual summaries; OANDA Journal sync/table all pass.
- No page overflow or observed application runtime exception. Smoke selector
  assumptions about async strategy loading/default XAU symbol were corrected;
  no application change was needed for those smoke-script failures.
- Evidence: `%TEMP%/ledger-cp8-execution-smoke-dbfipeja/`.

Manual acceptance:

1. With licensed Massive data, load NQ1! at each intraday timeframe. Check the
   displayed dated contract, schedule version and transitions around real rolls.
2. Compare raw vs adjusted charts; verify Backtest and Replay continue to use raw
   dated prices regardless of chart adjustment setting. Try a funded synthetic
   account sufficient for the existing full-notional limits.
3. Run NQ1! ORB on a known session; inspect executed_contract, tick, quantity and
   multiplier in the saved trade. Check a flat multi-session run spanning a roll.
4. Try an open cross-roll position and an unfilled pre-roll order: respectively
   expect rejection/termination and cancellation, never a synthetic transfer.
5. Close a Replay trade and inspect both Journal identities/P&L. Edit review and
   confirm the record ID and contract metadata survive.
6. Run the offline comparison on licensed exports before claiming TradingView
   alignment. Missing bars, unknown contract annotations and provider delays must
   remain visible limitations. Complete real-account Portfolio acceptance from
   the part-1 checklist separately.
