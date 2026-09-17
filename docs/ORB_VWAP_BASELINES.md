# ORB and VWAP baseline v1.0

Formulas fixed before implementation; no historical performance tuning.

Both strategies require completed one-minute bars, US equities or supported
dated futures, and every minute from 09:30 America/New_York to the decision.
Missing minutes disable signals for that session. Prices remain UTC internally.
Continuous futures and OANDA tick-volume instruments are not eligible. Signals
expire at 16:00 New York; position exits still obey the configured common engine
overnight/force-close settings. This is a cash-session research window, not an
exchange holiday/early-close calendar.

## Opening range breakout

`opening_range_breakout_baseline_v1`: high/low of the 15 bars starting
09:30 through 09:44. A subsequent completed close strictly above the range
high confirms long; strictly below the range low confirms short. Entry is the
next available bar open before 16:00. Stop is the opposite range edge; target
is 2R from the actual entry. At most one signal attempt per direction/session,
including rejected attempts: this conservatively guarantees at most one trade.
No volume, ATR or trend filters in the frozen baseline.

`opening_range_breakout_research_v1` is explicitly experimental. Parameters:
range_minutes 5/15/30 (15), confirmation close/wick (close), target_r (2),
entry_mode direct/retest (direct), volume_ratio (0/off), min_range_atr (0/off),
trend_ema_length (0/off). Retest is a persistent limit at the original broken
edge, expiring 15 clock minutes after confirmation (at most 15 subsequent
one-minute bars). Wick breaks on both sides are rejected.
Volume compares breakout volume to the preceding 20 bars' mean, excluding the
breakout. Range/ATR uses the preceding 14 simple true ranges (15 prior bars).
Trend compares completed close to the causal session EMA, requiring at least
its configured number of observations. Filters require sufficient history.
Research settings never silently change the baseline registry identity.

## VWAP mean reversion

`vwap_mean_reversion_baseline_v1`: typical price p=(H+L+C)/3; weight is traded
bar volume v. Since 09:30, W=sum(v), VWAP=sum(v*p)/W and population variance
sum(v*(p-VWAP)^2)/W. Weighted Welford accumulation avoids cancellation. Bands
are VWAP +/- 2 population standard deviations, including the completed decision
bar. Zero volume has no weight; invalid prices/negative volume are rejected.

A completed close strictly outside a band arms a setup toward VWAP. A later
completed close strictly inside both current bands confirms it. The structural
stop is the minimum low (long) or maximum high (short) observed from excursion
through confirmation. An opposite excursion replaces the armed direction.
Entry is next-bar open. Target is VWAP frozen at confirmation, rounded toward
entry to a valid tick for futures. Confirmation already beyond target is
recorded as rejected; an invalid next-open stop/target is rejected by the engine.
State resets each cash session. No trailing/partial exit or added daily limit.

`rth_vwap_bands` exposes a selectable vwap/upper/lower/sd line through the
existing indicator interface. It needs data from 09:30 for a full-session
value; a truncated chart contains only the available volume. Strategies require
the complete anchor. Existing VWAP indicator behavior is unchanged.

## Execution and limitations

Common engine sizing, contract multipliers, costs, fill policy and account
constraints apply. No strategy-owned accounting. MFE/MAE diagnostics exclude
exit-bar extremes whose ordering is unknown; they are explicitly lower bounds.
Trade outcomes are added only after simulation, never used for signals.

Provider coverage remains unverified by synthetic tests. Alpaca IEX volume is
not consolidated market volume. Futures use dated contracts and full-notional
capital constraints, not a broker margin model. No roll/portfolio optimization,
point-in-time stock universe, fundamentals or survivorship-free claim is added.
Historical universe may contain survivorship bias. No database migration.

## Checkpoint 5 handoff (2026-09-17)

Implemented after checkpoint 4 commit `ffb2217`. Checkpoint 6 has not started:
the complete Gold variant family and comparison view remain the next phase.
Checkpoint 7 remains the final release-wide report. Frozen Gold/Momentum,
Replay, Journal, provider routing and user data are unchanged in this checkpoint.

Changed files:

- backend/app/backtesting/engine.py
- backend/app/backtesting/models.py
- backend/app/services/backtest.py
- frontend/src/features/strategy-lab/TradeAuditChart.jsx
- docs/RELEASE_CHECKPOINTS.md

New files:

- backend/app/backtesting/strategies/intraday_baselines.py
- backend/app/backtesting/intraday_reporting.py
- backend/app/indicators/rth_vwap.py
- backend/tests/test_intraday_baselines.py
- docs/ORB_VWAP_BASELINES.md

The generic engine extension is opt-in `EntrySignal.expires_at`, an exclusive
deadline checked before any fill. Existing signals default to None. Deadline-aware
signals also retain a detected setup when configured session flattening blocks
entry. Sizing, costs, existing pending-order behavior and same-bar policies stay
unchanged. New strategy outcomes and full canonical parameters are persisted in
the existing saved-run JSON. Trade Audit adds static OR/VWAP levels and markers;
no chart infrastructure or database schema changes.

### Exact verification

From backend, with fresh temporary pytest directories:

```powershell
.venv/Scripts/python.exe -m pytest -q tests/test_intraday_baselines.py -p no:cacheprovider --basetemp "$env:TEMP/ledger-cp5-focused-$([guid]::NewGuid().ToString('N'))"
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp "$env:TEMP/ledger-cp5-full-$([guid]::NewGuid().ToString('N'))"
```

- Focused new strategy suite: **46 passed**, 7.99 seconds.
- Full backend: **366 passed**, 46.44 seconds, two existing Starlette/httpx and
  AnyIO deprecation warnings. Includes engine, futures, frozen XAU, Momentum,
  Replay, broker safety, Journal and preservation regressions.
- Frontend `node --test tests/*.test.js`: **12 passed**, zero failures.
- Frontend `npm.cmd run build -- --outDir "$env:TEMP/ledger-cp5-build-final"`:
  **passed**, 68 modules, 4.82 seconds. Existing large-chunk warning remains.
- `git diff --check`: passed; no generated data, credentials or caches added.

Deterministic tests cover completed bars, exact hand-worked trades, long/short
mirrors, prefix equivalence under future mutation, DST/session anchoring,
missing minutes, exclusive deadlines, both same-bar policies, frozen parameters,
research filters/retests, weighted population math, zero/invalid volume, next-open
gaps, futures contract/tick handling, saved snapshots and conservative excursions.
Initial fixture failures were corrected: favorable target gaps use the engine's
existing opening fill; a wick-only test must not include a later valid excursion.

Isolated headless Chrome with synthetic bars, temporary SQLite and blocked
external HTTP verified ORB baseline and research runs, research controls, VWAP
run, all three saved snapshots, both Trade Audit views, indicator discovery,
and no page overflow at 1024 x 900. No observed application runtime exception.
Two smoke-script waits initially used incorrect display text/casing; corrected
waits passed without application changes. Evidence and helpers are under
`%TEMP%/ledger-cp5-smoke-rsaj5amv/`. No live market/broker validation was performed.

### Manual acceptance

1. Backtest: select Opening Range Breakout baseline, a liquid US stock or a
   supported dated futures contract, primary 1m and a period with provider data.
   Set realistic account capital/costs; futures require full-notional capital.
2. Verify a 09:30-09:44 range, completed breakout, subsequent open entry,
   opposite-edge stop and 2R target. Inspect range levels/markers in View chart.
3. Select the separately labeled experimental ORB variant. Change just one
   parameter; confirm the saved run retains its experimental key and settings.
4. Run VWAP baseline; inspect excursion, confirmation bands, structural extreme,
   subsequent entry and frozen VWAP target. Compare with the documented formula.
5. Reopen both saved runs without rerunning; confirm audit details and warnings.
6. In the indicator interface use `rth_vwap_bands` with line vwap, upper, lower
   or sd (deviations 2). Load the full 09:30 session anchor for complete values.
7. Check the date range, costs, overnight setting and sample size before drawing
   any conclusions. These are research baselines, not evidence of an edge.

Remaining limitations: strict minute completeness can suppress sparse-feed
sessions; early closes need explicit run guardrails; ORB limits attempts, not
only successful fills; MFE/MAE are lower bounds; long-history throughput has not
been benchmarked. No real futures coverage or consolidated equity volume was
validated. Gold variants/comparison and the final release report remain pending.
