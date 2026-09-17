# Gold experiments v1 — definitions frozen before implementation

These are filter experiments, not optimization. The existing Gold v1.1 file,
default parameters, setup state machine, 50% persistent limit, structural stop
and 1.5R target remain unchanged. Each experiment delegates to that baseline.
No new order/account arithmetic. All measurements use completed bars only.
Missing required history rejects a detected setup with a recorded reason.

Registry prefix: `xau_type3_experiment_`, suffix `_v1`.
Identities: reference, fvg, dxy, session, compression, displacement, htf,
overextension, sweep_depth, fvg_displacement, dxy_session, full_candidate.
Experiment defaults are fixed; use a new version for subsequent hypotheses.

## Exact filters

ATR means the simple mean of 14 true ranges from the 15 completed one-minute
bars immediately BEFORE the confirmation bar. TR=max(H-L, abs(H-Cprev),
abs(L-Cprev)). No confirmation-bar range in the ATR denominator.

- FVG: inspect consecutive, contiguous three-minute candles from the original
  sweep through confirmation. Bullish gap if candle 3 low > candle 1 high;
  bearish gap if candle 3 high < candle 1 low. The unchanged baseline entry must
  lie within that gap, inclusive. After gap creation, a long gap is invalidated
  by any low <= its lower edge; short by any high >= its upper edge. At least
  one unfilled overlapping directional gap must survive at confirmation.
- DXY: latest completed DXY 1h close below its EMA20 AND EMA20 below its value
  three completed hours earlier for Gold long; mirror for short. At least 23
  completed hourly observations; latest close available no more than 2 hours
  before the Gold decision; last four hourly starts must be contiguous. EMA
  uses adjust=False. No proxy substitution. Ledger currently has no verified DXY
  provider path: DXY, DXY+session and full-candidate identities explicitly reject
  with `dxy_data_unavailable`. Their zero-fill results are NOT performance evidence.
- Session: confirmation-bar start is in [08:00,12:00) Europe/London OR
  [08:00,12:00) America/New_York, with local DST rules.
- Compression: 20 consecutive completed minutes BEFORE the original sweep.
  Range(last 10)/range(first 10) <= 0.65; range=max(H)-min(L); positive
  denominator required. The sweep and confirmation never enter this window.
- Displacement: confirmation candle has directional body / prior ATR >= 1.0
  and close location >= 0.75 toward its directional extreme. Long location
  (C-L)/(H-L), short (H-C)/(H-L); H>L and matching candle direction required.
- HTF: latest completed Gold 1h close above EMA20 and EMA20 above its value
  three completed observations earlier for long; mirror for short. At least 23
  completed observations. This is an EMA proxy, not discretionary structure.
- 20m overextension: 21 consecutive completed one-minute closes ending at
  confirmation; directional movement Cnow-C20ago (mirror short) / prior ATR
  must be <= 3.0. Negative movement passes; missing minutes reject.
- Sweep depth: original sweep depth / prior ATR >= 0.25.
- Combinations apply all constituent filters. Full candidate applies all eight.

All threshold comparisons are inclusive except directional EMA/body conditions.
Audit stores each filter's measurements, status and reason plus baseline metadata.

## Comparisons and validity

Compare saved immutable snapshots only; never rerun or rank automatically.
Matched baseline setup identity is symbol + direction + original sweep time +
confirmation time. Retained/removed percentages require matching input data and
engine configuration. Removed means explicitly failed filter, not simply absent
from the variant. Missing baseline identities and extra variant identities are
shown separately: rejecting one position can expose later setups that baseline
position occupancy suppressed. Such path dependence is not filter retention.

Data fingerprints cover loaded OHLCV, timestamps and availability columns.
Older runs without fingerprints cannot establish identical inputs. Baseline
comparison needs the experimental reference or unchanged frozen baseline with
matching defaults; mismatches disable retention percentages.

MFE/MAE are post-run lower bounds excluding unknown exit-bar ordering, measured
in initial R. Missing legacy measurements stay unavailable and their sample N
is explicit. Breakdowns use entry time in New York. Regime is shown only where
recorded; no retroactive regime classifier is invented. P&L is the engine's
account-currency result; comparisons must retain their configuration context.

## Checkpoint 6 verification and handoff

2026-09-17, based on checkpoint 5 commit ff93317. No database migration, user data
changes, market-provider routing changes or edits to the frozen Gold/Momentum
strategy files. The engine and Replay implementation are unchanged.

Changed: `backend/app/services/backtest.py`,
`frontend/src/features/strategy-lab/StrategyLabPage.jsx`,
`docs/RELEASE_CHECKPOINTS.md`.
Added: `backend/app/backtesting/strategies/gold_experiments.py`,
`backend/app/backtesting/gold_reporting.py`,
`backend/tests/test_gold_experiments.py`,
`frontend/src/features/strategy-lab/RunComparison.jsx`,
`frontend/src/features/strategy-lab/runComparison.js`,
`frontend/tests/runComparison.test.js`, `docs/GOLD_EXPERIMENTS.md`.

Verification commands (backend pytest uses unique temporary basetemp and no cache):

- `python -m pytest -q tests/test_gold_experiments.py -p no:cacheprovider --basetemp <temp>`:
  **42 passed**, 5.15s, including exact reference equivalence, all 12 identities,
  threshold boundaries, symmetry, future-mutation prefix equivalence, DXY
  stale/missing/causal handling, immutable snapshots and fingerprint differences.
- `python -m pytest -q -p no:cacheprovider --basetemp <temp>`: **408 passed**,
  51.35s, two existing dependency deprecations.
- `node --test tests/*.test.js`: **17 passed** (5 new comparison utility cases).
- `npm.cmd run build -- --outDir <temp>`: **passed**, 70 modules, 1.47s.
  Existing large-bundle warning remains. Initial Windows extension-resolution
  failure was fixed with explicit component/helper import extensions.
- `git diff --check`: passed.

Isolated Chrome, synthetic data, temporary SQLite, external HTTP disabled:
all 12 saved identities selected simultaneously; reference selector, complete
metric table, retention, DXY-unavailable warning and year breakdown passed.
No observed runtime exception or page overflow at 1024px. Evidence:
`%TEMP%/ledger-cp6-smoke-o0ht6_w2/gold-comparison.png`.

Manual acceptance: create a reference run and one filter run with identical
period, costs and sizing. In Runs select both (up to 12), inspect reference and
retention, then change costs and confirm retention becomes unavailable. Check
individual Trade Audit metadata. Inspect session/direction/weekday/month/year/
regime breakdowns. Missing legacy fingerprints/excursions stay unavailable.
Run DXY-dependent identities only to inspect their unavailable-data diagnostics;
they cannot establish strategy performance until a verified DXY feed is added.

No historical performance was used to select thresholds. Checkpoints 7 and 8
remain separate required work; this is not the final release acceptance report.
