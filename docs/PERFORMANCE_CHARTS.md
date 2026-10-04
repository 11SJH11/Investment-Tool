# Equity and drawdown comparison

The existing Lightweight Charts `PerformanceChart` now owns two panes on one
chart/time scale: equity/normalized return/cumulative R above, canonical account
percentage drawdown below. Pane proportions begin at 70/30. Crosshair, zoom, pan
and dates are coordinated by the same chart instance.

## What changed

- Single-run Summary and expanded performance both use the coordinated chart.
- Runs selection and Activity batch comparison support up to 30 selected runs.
- Comparison loads saved summary projections with at most three concurrent
  requests. Curves and headline metrics load first. The existing trade-level
  metrics, retention and breakdowns load through an explicit details action.
- Every run retains its assigned palette colour across panes, legend, hover
  readout and metric headers during the comparison. After 15 colours, secondary
  line styles distinguish repeated colours. Hover/focus emphasizes a run;
  visibility, isolate and show-all controls do not mutate saved results.
- Default view fits the entire union of recorded dates. Runs stop at their own
  endpoints. Hover uses the last recorded observation inside a run's boundaries
  and labels it when it precedes the shared cursor; outside those boundaries it
  shows no observation. No series is extended beyond its end.
- Equity is explicitly labelled account units because older records do not always
  preserve an account currency. Normalized return uses each run's own starting
  balance. Check currencies/capital before comparing absolute equity.
- Existing unsupported DXY experiment warnings still suppress performance claims.

## Root cause and full-history behaviour

The old component already called `fitContent`, but default minimum bar spacing
could clamp long minute histories to a smaller window. Separate chart instances
also had independent scales and crosshairs. Comparison previously rendered only
metrics and capped selection at 12.

The new chart allows sufficiently small spacing and explicitly selects the full
union domain. Browser inspection additionally found that widening a previously
narrow chart could preserve small pixel spacing, leaving blank area despite
correct time bounds. Full-history mode now refits after the library completes a
resize. Manual zoom/pan disables automatic refitting until Full range / Reset zoom.

## Accuracy and performance

Saved `drawdown_pct` is authoritative. For legacy summary snapshots missing
return/drawdown fields, the repository's read-only projection invokes the existing
engine `_decorate_equity_curve` helper and preserves all already recorded fields.
No second frontend drawdown formula, database migration, result rewrite, strategy
change, accounting change or rerun is introduced.

The frontend sorts observations and retains the last sample at duplicate timestamps.
Only interiors of exactly unchanged equity/return/drawdown/R plateaus are omitted
from rendering. Plateau edges, peaks, troughs, recovery transitions, start/end
points and trade events remain. There is no averaging or approximate smoothing.
Full-resolution observations remain available to logarithmic-time hover lookup.
Derived curves are memoized; hover updates compact legend values without rebuilding
series. If the first observation already differs from starting capital, an explicitly
labelled initial-balance anchor one second earlier supplies the zero-return origin.
It is an account reference, not a fabricated market observation.

The browser fixture spans 2015-01-01 through 2026-01-15, with 15 runs and 300,000
observations. Fixture generation, JSON transfer/parsing and chart readiness together
measured approximately 7.2-9.0 seconds locally across passes. This is synthetic,
not a live-provider benchmark. The full union and rendered endpoint coordinates
were checked, including after resizing. Highly variable multi-million-point runs
still consume significant browser memory/time: exactness was retained over lossy
sampling. A longer backtest is never restricted to a short default date window.

## Verification (2026-10-04)

- Full backend suite: **789 passed**, 86.63 seconds.
- Full frontend utility suite: **106 passed**.
- Production build: **passed**, 130 modules, 1.15 seconds.
- Focused backend projection/preservation checks: **2 passed**.
- New curve utilities: **9 passed**, covering 1/2/5/10/15/30 runs, union dates,
  stable styles, out-of-range hover, exact drawdowns/plateaus, normalization and
  bounded request concurrency.
- Browser: 15 runs/300,000 observations, single-run viewer, actual time and pixel
  bounds, hide/show/isolate, stable colours, wheel zoom/reset and no page overflow
  at 390/1024/1440/1920px. No runtime errors. Screenshot inspected for pane alignment
  and the resize regression. Real mobile hardware/touch was not tested.
- The canonical fixture starts at 100, ends at 130, and has a -25% worst drawdown;
  projected chart values match the engine/summary and saved snapshots stay unchanged.
- Existing large-bundle and Starlette/httpx deprecation warnings remain.

Run the normal isolated `Verify-Ledger.ps1` gate. The opt-in mocked browser script
is `frontend/tests/browser/equity-comparison-smoke.mjs`; set `LEDGER_CDP_URL` to an
isolated Chrome debug endpoint and `LEDGER_SMOKE_URL` to the production build.
Optional `LEDGER_SMOKE_OUTPUT` receives its screenshot. No live data or credentials
are needed and no live Ledger process was restarted.

## Manual test

1. Open any saved run. Summary should show equity and drawdown together, covering
   its complete history. Check start/end equity and worst drawdown against metrics.
2. Switch Equity / Return / Cumulative R; account drawdown stays a separate percent
   pane. Expand performance and confirm both panes remain present.
3. In Runs, select 2, 5, then 15 or more arbitrary runs. Their curves and headline
   metrics should appear without loading all trade-level analysis first.
4. Compare runs with different dates and capital. Start with normalized return;
   verify the union dates and that shorter runs do not extend into other periods.
5. Hover either pane; inspect same-colour legend readouts. Hide a run, isolate
   another, then Show all runs. Hover/focus a legend entry to emphasize its curves.
6. Zoom with wheel/pinch or pan. Both panes must move together. Press Full range /
   Reset zoom. Resize narrow then wide: the full history should still fill the chart.
7. Load detailed metrics, retention and breakdowns; existing comparison warnings
   and statistics should remain available for the same selection.
