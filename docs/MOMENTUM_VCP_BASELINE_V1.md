# Momentum / VCP Breakout baseline v1.0

Frozen registry key: `momentum_vcp_breakout_baseline_v1`. Price and volume only;
long US equities, daily bars. Defaults are an untuned research specification,
not a claim of profitability. Overrides are saved with each run and are experiments.

## Specification agreed before implementation

Require 250 completed bars **before** breakout bar N. The requested data period
includes warm-up; no hidden pre-period data is fetched. Trend on completed N:
C > EMA20 > EMA50 > SMA200; SMA200[N] > SMA200[N-20]. EMA uses pandas causal
adjust=False span smoothing; SMA is a full-window arithmetic mean.

Prior 20 bars (excluding N): mean(close * volume) >= $20,000,000. Momentum:
100*(C[N]/C[N-60]-1) > 0. Near high: 100*(H60-C[N])/H60 <= 5, where H60 is
max(high[N-60:N]); a close above H60 has negative distance and qualifies.

Select the **longest qualifying** base, trying lengths 30 down through 10,
each ending N-1. Pivot = maximum base high; base low = minimum base low;
depth = 100*(pivot-base_low)/pivot <= 15. Each candidate must pass both
contraction rules. Selection uses only pre-N data. After selecting this base,
require close[N] > its pivot; do not fall back to a shorter base if it fails.

For each base bar i, TR[i] = max(H[i]-L[i], abs(H[i]-C[i-1]),
abs(L[i]-C[i-1])); TR%[i] = 100*TR[i]/C[i-1]. The ATR% proxy is the
arithmetic mean of these daily TR percentages (not Wilder smoothing).
Recent window = final 5 base bars; early window = all other base bars
(L-5). Require recent ATR% / early ATR% <= 0.75; early ATR% must be positive.
Require mean(recent volume)/mean(early volume) < 1.0; early volume > 0.
Neither contraction calculation includes breakout bar N.

Breakout requires completed close[N] > pivot AND volume[N] > 1.0 * mean
volume[N-20:N]. All passing breakouts create setup records, including ones
with no confirmed stop, an existing position, an engine filter, or no next bar.
Select the most recent strict swing low in the base, lower than both 2 left
and 2 right neighbours. All five bars must be inside the base and completed
before N. Equal lows do not form a confirmed pivot.

Market entry is next provided session's daily open. Require raw open > pivot
and raw open <= pivot*1.02; equality at pivot rejects as failed before fill.
After existing engine spread/slippage, require 100*(entry-stop)/entry <= 8.
No structural stop means no entry; never substitute a percentage stop.
Initial target = actual cost-adjusted entry + 2*(entry-stop). The common engine
owns size, commissions, exposure, gap fills and same-bar ordering. No trailing,
partials, fundamentals, leverage override or custom execution model.

## Daily data and architecture

The plugin is discovered by the existing registry. No indicator registration,
database migration, market-data routing, Gold rule or Replay change is needed.
Only optional common-engine entry constraints and explicit bar availability
are required. Existing callers retain their execution contract.

Alpaca provider-native daily bars are dated at New York midnight. In this
strategy's local backtest frames only, their modeled open timestamp is 09:30 NY;
availability is conservatively the following NY midnight. This waits for the
whole provider daily bucket, including volume updates. It is an end-of-day
decision for N, eligible to fill at N+1 open, never an intraday breakout fill.
Daily timestamps label modeled sessions, not observed auction/execution times.
Incomplete daily buckets are excluded. Early closes still wait until midnight.
Entry time/day filters apply at the next open, not at the overnight decision.
Intraday flattening and extra intraday context are unsupported for this baseline.

Alpaca defines daily buckets and trade-condition eligibility in its
[Market Data FAQ](https://docs.alpaca.markets/us/docs/market-data-faq).
Ledger uses configured feed and adjustment unchanged (normally SIP, split);
both are saved. Daily OHLC and volume follow provider eligibility, not a
locally reconstructed regular-session auction series. IEX is one venue, so
volume/liquidity results differ. Split-adjusted bars are not a total-return
series. Provider corrections or corporate actions can change a later rerun.

The existing engine already supports an explicit list of up to 20 symbols:
one shared starting balance, configured risk sizing, maximum positions and
leverage/exposure limits, alphabetical ordering for simultaneous fills, one
position per symbol, fractional quantities. Risk sizing uses realized balance;
existing positions consume exposure. Costs, guardrails and same-bar ordering
remain the configured engine assumptions. These are portfolio results for the
specified list, separate from setup counts; they are not universe scan statistics.

The symbol directory/screener is **current-universe only**, refreshed from active
assets. There is no historical membership or security-master database, delisting
return handling, point-in-time fundamentals or portfolio selection/ranking system.
Alpaca may map historical ticker changes by its default asof behavior; Ledger
does not freeze that mapping. Missing daily bars are not synthesized, so next
provided session may skip a missing session. Young IPOs cannot qualify before
250 prior observations. ETFs cannot reliably be distinguished from stocks by
the current instrument classifier; the user must select US stock tickers.

Historical universe may contain survivorship bias.

No institutional-grade, survivorship-free universe performance is claimed.
Next phase: a versioned point-in-time security master/calendar and corporate-action
validation, then explicit candidate selection and missing-data policies using
the existing portfolio engine. Do not invent historical membership.

## Diagnostics and future experiments

Setup records retain conditions at N and separate later fill/outcome metadata.
MFE/MAE are conservative price excursions over completed held bars before the
exit bar plus known entry/exit prices. The unknown intrabar path on the exit bar
is excluded; these are lower bounds, not exact tick excursions. End-of-data
close exits can include the completed final bar. R remains engine net R after costs.

Do not implement these in v1: 3R, 10/21 EMA trailing, higher-low trailing,
partial 2R plus runner, stronger relative volume/strength, SPY/QQQ regime,
sector-relative strength, earnings/fundamentals, alternate base depths,
contraction thresholds or chase limits. Test one variable at a time with separate
variants and development, validation and out-of-sample periods.
