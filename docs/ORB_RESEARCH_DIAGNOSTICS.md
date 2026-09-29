# ORB research: causal volatility and participation

Applies only to `opening_range_breakout_research_v1`. The frozen ORB baseline,
VWAP rules, fill model, position sizing and costs are unchanged. The research
variant wraps its existing signal rules. Diagnostics attach to every emitted
setup, including rejections and unfilled setups, and propagate to filled trades.
The existing one-setup-per-direction-per-session policy remains unchanged;
rejecting a setup does not create repeated attempts later in the session.

## Definitions

All signal-bar measurements use the completed breakout candle. The opening
range is the unchanged 09:30 New York window of 5, 15 or 30 minutes.

| Metadata | Definition |
|---|---|
| `breakout_range` | High minus low |
| `prior_1m_atr14` | Wilder ATR of preceding completed, contiguous 1m bars; excludes breakout |
| `breakout_range_atr` | Breakout range / prior 1m ATR14 |
| `breakout_body` | Absolute close minus open |
| `breakout_body_ratio` | Body / candle range |
| `breakout_close_location` | (Close − low) / range; 0 at low, 1 at high, for both directions |
| `breakout_volume` | Reported completed breakout candle volume |
| `same_minute_volume_median20` | Median volume at the identical New York clock minute in the previous 20 completed daily sessions |
| `breakout_rvol` | Breakout volume / that same-minute median |
| `opening_range_volume` | Sum of current opening-range minute volumes |
| `opening_range_volume_median20` | Median of the 20 prior equivalent opening-range volume sums |
| `opening_range_rvol` | Current opening-range volume / that median |
| `previous_daily_atr14` | Wilder ATR14 ending at the previous completed provider daily bar |
| `previous_close` | Close of that same completed daily bar |
| `daily_natr_pct` | 100 × previous daily ATR14 / previous close |
| `daily_natr_percentile` | Percentage of the **60 preceding** daily NATR observations less than or equal to the latest completed daily NATR |

Wilder ATR seeds with the arithmetic mean of 14 true ranges requiring 15 bars,
then uses `(13 × previous ATR + current TR) / 14`. TR includes gaps from the
previous close. Intraday ATR resets after an observation-time gap; invalid daily
OHLC breaks the daily seed. Percentile comparisons exclude the latest NATR
itself and require 60 valid comparisons, so at least 75 daily bars are needed.
Ties use the inclusive empirical percentile. Nothing uses the current day's
unfinished daily candle.

New York local clock time, not UTC clock time, aligns volume across DST.
Provider daily observations identify historical sessions. A missing minute in
those 20 sessions is not replaced by an older session. All equivalent opening
range minutes must exist exactly once. Zero denominators, insufficient history
and missing observations yield null, never a fabricated value or future data.
Known intraday sessions absent from daily history invalidate the daily/session
reference rather than compressing the window.

## History and causality

Only research runs request a 200-calendar-day daily warmup and a separate
60-calendar-day intraday warmup. Intraday warmup bars **never enter the engine's
execution timeline** and cannot create trades before the requested start.
Diagnostic history is additionally clipped before the first execution-period
bar and to completion at the signal. Normal `StrategyContext` completion gates
exclude future execution-period and daily bars.

US equity daily bars use Ledger's existing daily completion normalization.
Futures retain provider daily completion/session labels; these are provider
daily sessions, not fabricated equity cash-session daily bars. Volume still
compares the 09:30 New York opening range and identical local breakout minute.
Provider coverage, adjustment and volume conventions remain material research
limitations. A day absent from both daily and intraday feeds cannot be
distinguished from a market closure without an independent exchange calendar.

Optional history fetch failures add a sanitized warning. Default-off runs still
execute their original rules; enabled filters reject unavailable measurements.
If intraday warmup is unavailable, sufficient history within the requested run
can subsequently populate RVOL. Direct strategy/test use without daily input
returns null for the daily-dependent diagnostics. No migration or rewriting of
saved runs occurs; old runs display unavailable fields.

## Optional filters

All six thresholds default to **−1 (OFF)**. Set a threshold to zero or above to
enable it; zero is a real enabled threshold, not a substitute for missing data.

- `min_breakout_range_atr`
- `min_breakout_body_ratio` (0–1)
- `min_breakout_rvol`
- `min_opening_range_rvol`
- `min_atr_regime_percentile` (0–100)
- `max_atr_regime_percentile` (0–100)

Comparisons include the boundary. An enabled filter rejects null/nonfinite
measurements with `<parameter>_unavailable`; a failed comparison records
`<parameter>_filter`. Existing rejection reasons take precedence. Minimum regime
percentile cannot exceed an enabled maximum. These new filters do not replace
the legacy prior-20-bar volume or opening-range/ATR filters.

## Research workflow

Run the research variant with all new filters off first. In Run Viewer →
Analysis → **ORB volatility / participation**, select any of the 16 metrics.
Fixed buckets show N, valid-R N, average/total R, PF, win rate and MFE/MAE with
their own sample sizes. Unavailable values have a separate bucket; N < 20 is
labelled low sample. These are filled-trade cohorts, not all detected setups.
Price and absolute-volume buckets are instrument-specific; do not pool unlike
instruments or providers. No bucket is labelled optimal.

Trade CSV automatically includes these scalar fields as `meta_<field>` plus
the complete metadata JSON. Full-run JSON preserves setup diagnostics and
rejection reasons even for setups that did not become trades. Use a fresh run
to collect new fields; existing saved results are not recalculated.

Manual checks: compare default-off trade executions with a prior research run;
inspect metadata on both a filled and rejected setup; verify 09:45 volume
against prior 09:45 observations across DST; enable one threshold at a time;
inspect Analysis and exported `meta_` columns. Parameter optimization is outside
this change.

## Verification

- Focused backend (`test_orb_participation.py` and unchanged
  `test_intraday_baselines.py`): **74 passed**.
- Full backend: **551 passed**; one existing Starlette/httpx deprecation warning.
- Full frontend Node suite: **70 passed**.
- Frontend production build: passed; existing bundle-size advisory remains.
- Isolated mocked-data browser smoke: all 16 bucket choices, diagnostic CSV
  fields, legacy rendering and existing Journal/Portfolio exports passed with
  no runtime exceptions. Analysis has no page overflow at 1024/1440/1920px.
- Frozen ORB and VWAP class source compared exactly with the pre-task index:
  unchanged. Disabled-filter execution facts match the prior research rules.

Tests cover future-bar exclusion, unfinished daily candles, DST-local minute
matching, exact 20-session volume medians, missing minutes/sessions, zero volume,
ATR seed/history limits, percentile reference exclusion, all six filter bounds,
rejected setup metadata, trade propagation and warmup isolation. Provider-path
warmup failures are tested with fixtures; no real user databases or credentials
are used.
