# Strategy review notes — 30 Sep 2026

## Purpose
Static review of the strategy files supplied for the next broad screening phase. These files were checked for syntax and for whether their mechanics match the intended first-pass hypotheses discussed in chat. This is not a replacement for Ledger's full backend regression suite.

## Files changed

### turtle_donchian_research_v1.py
Changed the screening defaults/mechanics to match the intended simple Donchian test:
- default signal timeframe: **15m** (was 1h)
- entry: completed close beyond the previous 20-bar channel
- initial stop: 2 ATR from the signal close
- default EMA filter: **off** (was EMA 200)
- exit: completed close through the opposite previous 10-bar channel
- **removed the default ATR trailing stop**; the earlier file was testing a materially different strategy
- no pyramiding
- optional research fixed-R target remains available and is expressed as `target_r` so it is based on the actual fill/initial stop

This now matches the simple screening hypothesis: 20-bar Donchian breakout / 10-bar exit / 2 ATR initial stop, with no extra trend filter or trailing rule by default.

### open_session_atr_breakout_research_v1.py
Two correctness fixes:
- session-bar timestamps now come from the explicit `timestamp` column rather than assuming the DataFrame index is a datetime
- fixed-R target is now passed as `target_r`, so Ledger calculates it from the actual next-bar fill to the initial stop rather than freezing an absolute target from the signal close
- added session-end expiry to avoid a late signal filling after the configured session

The intended baseline remains: session open +/- 0.10 completed daily ATR, 15m signal bars, first confirmed breakout of the day, session-open stop, 2R target.

## New file

### poc_reclaim_retest_research_v1.py
Implements the mechanical first-pass AMN/POC reclaim-retest hypothesis on **5m** bars:
1. longest immediately preceding compressed accumulation of 15–40 contiguous 5m bars
2. accumulation width <= 1.5 x prior 5m ATR(14)
3. sweep beyond the frozen accumulation edge by >= 0.05 ATR
4. re-entry and reclaim of frozen POC proxy within 12 bars
5. POC retest/hold within 10 bars
6. next-bar market entry
7. stop at observed sweep extreme
8. target 2R from actual fill to initial stop

### Critical POC limitation
The supplied Ledger data model is OHLCV bars. OHLCV does **not** contain exchange volume-at-price, so it cannot produce a true market-profile POC. The new strategy deliberately calls its level a **POC proxy** and computes it as a volume-weighted histogram of each bar's HLC3 typical price.

This avoids pretending the backtest has information it does not have. If Ledger later gains tick/trade or volume-at-price data, replace the POC source and compare the same setup with a true POC.

## Reviewed but intentionally not changed

### intraday_baselines.py
- ORB / ORB research / Failed ORB logic was left untouched because you have already parity-tested and used it extensively.
- Existing VWAP baseline is a coherent but *specific* baseline: close outside 2-sigma session VWAP bands, then completed close back inside, next-bar entry, excursion-extreme stop, frozen VWAP target. It does **not** include a separate post-open waiting period. Do not describe it as such when interpreting results.

### momentum_vcp_breakout_baseline_v1.py
No obvious causal mismatch found in static review. Important: this is a **daily long-only VCP/momentum breakout**, not the intraday first-pullback momentum strategy discussed later. It should be screened across a predefined liquid-stock universe rather than treated as a direct SPY intraday strategy.

### xau_liquidity_type3.py / gold_experiments.py
No change made. The XAU Type-3 baseline is a different, gold-specific liquidity/structure strategy. DXY variants intentionally reject when a verified DXY data path is unavailable.

### base.py / registry.py / orb_participation.py / reference.py
No change required from this static review. `reference.py` and the Turtle implementation demonstrate that Ledger already supports `ManagePositionSignal`, including stop changes; a future ORB break-even test therefore probably needs strategy/config wiring rather than a brand-new engine primitive.

## Suggested first-pass screening settings

- **ORB C2:** keep frozen candidate; 1m; 15m OR; breakout ATR [1.5,2.0); opening RVOL <1.25; 2R
- **VWAP baseline:** existing frozen baseline; 1m
- **Turtle/Donchian:** revised defaults; 15m; 20 entry / 10 exit / ATR20 / 2 ATR stop / EMA off
- **Open-session ATR:** revised defaults; 15m signal; daily ATR14; 0.10 ATR band; session-open stop; 2R
- **POC reclaim-retest:** new file; 5m; defaults as encoded
- **Momentum/VCP:** daily; use a predefined liquid equity universe, not just SPY

For every new family, treat these as screening baselines. Avoid parameter sweeps until a baseline produces enough trades and at least a modest, stable signal worth investigating.
