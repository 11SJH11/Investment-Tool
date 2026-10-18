# VWAP confluence discovery report — optimized v2

## Contract

- Diagnostic only; no strategy rule was changed.
- Features use information available no later than the saved entry signal.
- Saved outcomes are immutable; market context is reconstructed from the current cache.
- Static subgroup results are **not** equivalent to a strategy rerun because of M3/path/replacement effects.
- Broad feature discovery creates multiple-testing risk. Prefer repeated cross-period relationships with a coherent market explanation.
- v2 precomputes causal pivots/BOS/FVG event indexes once per run; per-trade work is limited to causal lookups and bounded same-session liquidity scans.

## Runs

- **Run 182**: 2020-01-01 → 2023-09-02; 1679 trades; `vwap_trend_confirmation_quality_research_v5`; 0 cached sessions before run start; runtime 159.2s.
- **Run 179**: 2023-10-01 → 2025-12-31; 960 trades; `vwap_trend_confirmation_quality_research_v5`; 274 cached sessions before run start; runtime 124.9s.
- **Run 181**: 2026-04-01 → 2026-10-02; 214 trades; `vwap_trend_confirmation_quality_research_v5`; 276 cached sessions before run start; runtime 51.2s.

## Coverage

- Combined trades: **2,853**
- Feature columns: **1,246**
- Runs: **3**

### Warnings

- Run 182: only 0 cached RTH sessions precede the run; early time-of-day percentiles may be unavailable.

## Highest-priority diagnostic hypotheses

These are triage candidates, **not validated trading rules**.

| # | Variant | Family | N | Coverage | Δ avg R | Top-winner retention | Positive runs | Verdict |
|---:|---|---|---:|---:|---:|---:|---:|---|
| 1 | `fvg.opposing.unmitigated_touch.current.1m == false` | fvg | 1920 | 99.6% | +0.001 | 100.0% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 2 | `fvg.directional.recent30_ge_5bps.current.15m == false` | fvg | 2805 | 98.3% | +0.002 | 98.7% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 3 | `fvg.directional.recent30_ge_5bps.rolling.15m == false` | fvg | 2805 | 98.3% | +0.002 | 98.7% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 4 | `fvg.directional.recent30_ge_2bps.current.15m == false` | fvg | 2792 | 97.9% | +0.001 | 98.7% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 5 | `fvg.directional.recent30_ge_2bps.rolling.15m == false` | fvg | 2792 | 97.9% | +0.001 | 98.7% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 6 | `fvg.directional.recent30_ge_0bps.current.15m == false` | fvg | 2782 | 97.5% | +0.001 | 98.7% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 7 | `fvg.directional.recent30_ge_0bps.rolling.15m == false` | fvg | 2782 | 97.5% | +0.001 | 98.7% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 8 | `fvg.opposing.unfilled_full.current.1m == false` | fvg | 1872 | 97.1% | +0.001 | 98.0% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 9 | `fvg.directional.recent30_ge_0bps.current.1m == true` | fvg | 2441 | 85.6% | +0.000 | 89.6% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 10 | `fvg.directional.recent30_ge_0bps.rolling.1m == true` | fvg | 2441 | 85.6% | +0.000 | 89.6% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 11 | `fvg.directional.exists.current.1m == true` | fvg | 2446 | 85.7% | +0.000 | 89.6% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 12 | `bos.current.5m.s5.mss_proxy == false` | bos | 2847 | 99.8% | +0.002 | 100.0% | 2/2 | PROMISING_STABLE_DIAGNOSTIC |
| 13 | `bos.rolling.15m.s2.opposing_exists == true` | bos | 2851 | 99.9% | +0.001 | 100.0% | 1/1 | INTERESTING_NEEDS_REVIEW |
| 14 | `bos.current.1m.s1.directional_within_60m == true` | bos | 2318 | 81.2% | +0.000 | 83.1% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 15 | `bos.rolling.1m.s1.directional_within_60m == true` | bos | 2318 | 81.2% | +0.000 | 83.1% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 16 | `bos.current.1m.s1.directional_exists == true` | bos | 2319 | 81.3% | +0.000 | 83.1% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 17 | `fvg.opposing.unmitigated_touch.rolling.5m == false` | fvg | 2316 | 81.2% | +0.000 | 83.1% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 18 | `fvg.opposing.unfilled_full.rolling.1m == false` | fvg | 2567 | 90.0% | +0.000 | 90.9% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 19 | `fvg.directional.recent30_ge_2bps.current.1m == true` | fvg | 2154 | 75.5% | +0.000 | 81.8% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 20 | `fvg.directional.recent30_ge_2bps.rolling.1m == true` | fvg | 2154 | 75.5% | +0.000 | 81.8% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 21 | `structure.rolling.s2.all_1m5m15m_aligned == false` | structure | 2744 | 96.2% | +0.001 | 98.7% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 22 | `liquidity.or30l.taken_trade_direction == false` | liquidity | 776 | 87.7% | +0.001 | 87.0% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 23 | `fvg.opposing.unmitigated_touch.rolling.15m == false` | fvg | 2357 | 82.6% | +0.000 | 85.7% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 24 | `bos.current.15m.s5.directional_within_30m == false` | bos | 2713 | 95.1% | +0.001 | 96.1% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 25 | `bos.rolling.15m.s5.directional_within_30m == false` | bos | 2713 | 95.1% | +0.001 | 96.1% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 26 | `liquidity.prior_3d_low.taken_trade_direction == false` | liquidity | 673 | 76.0% | +0.001 | 82.6% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 27 | `fvg.opposing.unfilled_full.rolling.15m == false` | fvg | 2080 | 72.9% | +0.001 | 79.2% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 28 | `bos.current.1m.s2.directional_within_15m == true` | bos | 1805 | 63.3% | +0.000 | 68.8% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 29 | `bos.rolling.1m.s2.directional_within_15m == true` | bos | 1805 | 63.3% | +0.000 | 68.8% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 30 | `fvg.directional.recent30_ge_5bps.current.1m == true` | fvg | 1452 | 50.9% | +0.000 | 70.1% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 31 | `fvg.directional.recent30_ge_5bps.rolling.1m == true` | fvg | 1452 | 50.9% | +0.000 | 70.1% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 32 | `structure.rolling.15m.s2.aligned == false` | structure | 1766 | 61.9% | +0.000 | 71.4% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 33 | `bos.rolling.15m.s2.mss_proxy == true` | bos | 1766 | 61.9% | +0.000 | 71.4% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 34 | `bos.current.15m.s5.directional_within_15m == false` | bos | 2767 | 97.0% | +0.001 | 97.4% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 35 | `bos.rolling.15m.s5.directional_within_15m == false` | bos | 2767 | 97.0% | +0.001 | 97.4% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 36 | `fvg.opposing.unfilled_full.rolling.5m == false` | fvg | 2039 | 71.5% | +0.000 | 72.7% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 37 | `structure.rolling.1m.s5.aligned == false` | structure | 2024 | 70.9% | +0.000 | 77.9% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 38 | `bos.rolling.1m.s5.mss_proxy == true` | bos | 2024 | 70.9% | +0.000 | 77.9% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 39 | `fvg.directional.exists.current.15m == false` | fvg | 2730 | 95.7% | +0.001 | 96.1% | 3/3 | PROMISING_STABLE_DIAGNOSTIC |
| 40 | `liquidity.pmh.adverse_sweep_reclaim_0.exists == true` | liquidity | 238 | 26.9% | +0.000 | 30.4% | 2/2 | PROMISING_STABLE_DIAGNOSTIC |

## Definitions used

- **BOS:** first completed close through the latest already-confirmed strict swing level; one BOS per pivot.
- **Wick break:** first wick through that same already-confirmed swing; kept separate from close-BOS.
- **Sweep/reclaim:** wick beyond an already-known level and close back inside on the same bar or within the declared 1/3/5-bar horizon.
- **Swing sweep:** same-session sweep of one of the most recent confirmed swing levels from the current + previous structure-session window.
- **MSS proxy:** directional BOS while current two-sided structure is opposing or mixed. This is a research proxy, not a canonical CHOCH claim.
- **Structure:** strict unique 1/1, 2/2, 3/3 and 5/5 pivot variants on 1m/5m/15m; current-session and rolling prior-session views.
- **FVG:** same-session three-candle gap with first touch and full-fill times tracked causally.
- **Accumulation proxy:** explicitly heuristic combination of low 20m efficiency, high candle overlap, repeated VWAP crossings and volatility contraction. Inspect components separately.

## What to do next

1. Inspect `cross_run_stability.csv` before looking at the highest combined subgroup result.
2. Compare `top_winners.csv`, `top_losers.csv` and `fast_losses.csv` for mechanism and winner preservation.
3. Prefer a small number of coherent hypotheses such as `sweep → BOS → VWAP` over stacking correlated filters.
4. Implement one conceptual change at a time.
5. Rerun the **full Ledger engine** and inspect removed plus newly introduced replacement trades before accepting anything.
