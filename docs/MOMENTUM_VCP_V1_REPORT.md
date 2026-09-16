# Task 2 final report — Momentum / VCP Breakout baseline v1.0

Completed and verified on 2026-09-12. Task 1 passed its independent gate before
Task 2 began; see [Task 1 final report](JOURNAL_V2_STAGE_B_REPORT.md). No Journal
behavior was changed by Task 2. No real provider credentials, live orders,
historical performance optimization or user database were used.

## 1. Exact Task 2 files

Changed:

- `backend/app/backtesting/models.py` — optional entry bounds, fill-relative R
  target, structural-risk cap, rejected-setup reason and fill-time-only filters.
- `backend/app/backtesting/context.py` — optional explicit bar availability;
  existing duration-based behavior remains the default.
- `backend/app/backtesting/engine.py` — applies those optional constraints,
  records rejected setups/fill diagnostics, honors explicit completion timestamps.
- `backend/app/services/backtest.py` — new-strategy-only daily data contract,
  input validation, diagnostics/warnings and resolved parameter snapshots.
- `frontend/src/features/strategy-lab/StrategyLabPage.jsx` — daily strategy
  selection defaults, setup/outcome inspection, saved-run survivorship warning.
- `frontend/src/features/strategy-lab/TradeAuditChart.jsx` — metadata-only base
  pivot/low lines, base bounds/breakout markers, exit-bar alignment and daily dates.
- `frontend/src/features/strategy-lab/ValidationPanel.jsx` — survivorship and
  per-period warm-up warnings, including saved momentum experiments.

New:

- `backend/app/backtesting/strategies/momentum_vcp_breakout_baseline_v1.py`
- `backend/app/backtesting/momentum_reporting.py`
- `backend/tests/test_momentum_vcp_baseline.py`
- `docs/MOMENTUM_VCP_BASELINE_V1.md` — pre-implementation numerical contract.
- `docs/MOMENTUM_VCP_V1_REPORT.md` — this report.

No Task 2 migration/schema change. Existing saved-run JSON stores setup records,
resolved parameters, data warnings and outcomes. No change to Gold strategy
source, existing tests, provider routing, Alpaca provider, Replay code, drawing
infrastructure or Journal files. The engine extensions are optional and needed
to keep fills, risk sizing and accounting in the common engine.

## 2. Exact formula

The full causal contract is in [the frozen specification](MOMENTUM_VCP_BASELINE_V1.md).
For completed breakout bar N, require at least 250 prior observations; C[N] >
EMA20[N] > EMA50[N] > SMA200[N], and SMA200[N] > SMA200[N-20]. EMA is causal
adjust=False span smoothing; SMA uses complete rolling windows.

Prior 20-bar mean(C*V) >= $20m. Return = 100*(C[N]/C[N-60]-1) > 0.
Prior high = max(H[N-60:N]); distance = 100*(prior_high-C[N])/prior_high <= 5.
Negative distance means above the prior high and qualifies.

Try base lengths 30 down to 10, each ending N-1. Select the longest passing
candidate using only pre-N data. Pivot = max(base high); depth =
100*(pivot-min(base low))/pivot <= 15. After selection, a failed breakout close
does not cause a search for a shorter base with an easier pivot.
TR[i] = max(H[i]-L[i], abs(H[i]-C[i-1]), abs(L[i]-C[i-1])); TR%[i] =
100*TR[i]/C[i-1]. Recent ATR% proxy is mean(TR%) over the final 5 base bars;
early ATR% is the mean over the other L-5. Require recent/early <= 0.75 and
mean(recent volume)/mean(early volume) < 1. Both early denominators must be positive.

Breakout C[N] > pivot and V[N] > 1.0*mean(V[N-20:N]). All passing breakouts
are recorded. Stop is the latest strict 2-left/2-right low whose entire
confirmation window lies inside the pre-breakout base. Equal lows do not qualify.

Next provided session open O must satisfy pivot < O <= 1.02*pivot.
Apply engine market costs to obtain entry E. Require 100*(E-stop)/E <= 8.
Missing stop, failed open/chase/risk constraints, existing position, account/time
filters or absent next bar leave a detected setup without an entered trade.
Target = E + 2*(E-stop). No trailing, partials or stop movement. Generic engine
sizing, exposure, commissions, gap fills and same-bar policy remain authoritative.

## 3. All default parameters

The parameter table below is generated from the frozen plugin defaults. Target
R is fixed at 2.0 and cannot be overridden under this key. At least 250 prior
bars is enforced even if a caller attempts to lower minimum_history.

| Parameter | Default |
|---|---|
| `minimum_history` | `250` |
| `ema_fast` | `20` |
| `ema_medium` | `50` |
| `sma_long` | `200` |
| `sma_slope_sessions` | `20` |
| `liquidity_sessions` | `20` |
| `min_dollar_volume` | `20000000.0` |
| `momentum_sessions` | `60` |
| `min_return_pct` | `0.0` |
| `high_sessions` | `60` |
| `max_distance_high_pct` | `5.0` |
| `base_min` | `10` |
| `base_max` | `30` |
| `max_base_depth_pct` | `15.0` |
| `contraction_recent_sessions` | `5` |
| `max_atr_ratio` | `0.75` |
| `max_volume_ratio` | `1.0` |
| `breakout_volume_sessions` | `20` |
| `breakout_volume_multiple` | `1.0` |
| `max_chase_pct` | `2.0` |
| `swing_left` | `2` |
| `swing_right` | `2` |
| `max_stop_distance_pct` | `8.0` |

Default generic account configuration remains: $10,000 starting balance,
1% realized-balance risk, maximum 5 positions, 1x maximum exposure, fractional
quantities, zero configured commissions/slippage/spread, stop-first same-bar
policy and overnight holding. Costs and account controls must be set explicitly
for the intended research; zero defaults are not a claim that stock trading is free.
New entries are filtered at their next open; default weekdays are Monday–Friday.

## 4. No-lookahead guarantees

- Only context-completed bars enter the strategy; causal EMA/SMA cache values
  are sliced at the same boundary.
- Pivot/high comparison, base contraction, liquidity and breakout volume
  benchmark all exclude the breakout bar where required.
- The structural low is fully confirmed within the base before the breakout.
- The strategy never reads N+1. Common-engine next-open gates use only its open;
  stop and target management retains the engine's existing deterministic policy.
- Local daily frames model the open at 09:30 NY and expose the complete daily
  bucket at the following NY midnight. Incomplete buckets are excluded. Friday
  confirmation may be timestamped Saturday midnight but fills on Monday only.
- Daily execution timestamps are modeled session labels, not reconstructed
  intrabar/auction timestamps. Diagnostic outcome data is separate from setup
  conditions. Future-bar perturbation and prefix tests verify causal setup identity.

## 5–6. Data limitations and survivorship status

**Current-universe only. Historical universe may contain survivorship bias.**
This warning appears in results, saved-run lists/comparisons, validation and
saved momentum experiments. No historical symbol membership is fabricated.

The existing Alpaca historical path remains unchanged. Configured feed and
adjustment are retained in saved result provider metadata. Alpaca's daily bucket
and trade-condition rules, plus historical ticker-mapping behavior, are described
in its [official Market Data FAQ](https://docs.alpaca.markets/us/docs/market-data-faq).
Ledger does not freeze a point-in-time security master or the provider's default
ticker mapping. It has no delisting-return model. Split adjustment is normally
enabled; no dividends/total-return accounting or point-in-time fundamentals are added.
IEX is a single-venue feed, so liquidity and volume conclusions differ from SIP.

Missing sessions are never synthesized; next provided session may skip missing
data. IPOs need 250 prior observations. The current classifier cannot reliably
separate ETFs from common stocks, so users must select US stock tickers.
Provider data revisions/adjustments can change a later rerun. No institutional-grade
historical universe statistics are claimed.

Warm-up is inside each requested period, with no hidden pre-period fetch. Short
validation slices can produce no eligible setups. This is shown in the UI.
MFE/MAE are labeled conservative R lower bounds: completed held bars before the
exit bar plus known entry/exit prices; unknown exit-bar extremes are excluded.
Completed end-of-data exits include the final full bar. Exact intrabar excursions
and actual exit clock times cannot be recovered from daily OHLCV.

The engine already supports shared-capital runs over explicit lists of up to
20 symbols. It uses configured starting capital/risk, max positions and exposure,
alphabetical ordering for simultaneous fills and one position per symbol.
These are selected-list portfolio results, not a universe scan or historical
membership study. No scanner, portfolio semantics, fundamental filter or future
strategy experiment was introduced.

## 7. Exact final verification

All final checks below ran after implementation against the current source.
Counts overlap; do not sum them as unique tests.

| Check | Final result |
|---|---|
| Full backend suite | **193 passed**, 2 existing deprecation warnings, 22.27 s |
| New momentum suite | **45 passed**, 10.43 s |
| Explicit existing engine/context/saved-run/management/Replay/Gold selection | **37 passed**, 4.74 s |
| Existing Journal Node utility tests | **3 passed**, 0 failed |
| Frontend production build | **Passed**, 61 modules, 1.53 s |
| Final isolated browser build | **Passed**, 61 modules, 1.55 s |
| Final browser reload | Setup records, saved run, warning, actual audit canvas; 0 runtime errors; 1024px, no overflow |
| `git diff --check` | Passed |

Backend commands (from `backend`, using `.venv\Scripts\python.exe`):

```powershell
$taskTemp = Join-Path $env:TEMP ('ledger-task2-verified-full-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp $taskTemp --tb=short
```

The focused run uses a fresh `ledger-task2-pivot-focused-<GUID>` basetemp:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_momentum_vcp_baseline.py -q -p no:cacheprovider --basetemp $taskTemp --tb=short
```

The explicit regression run uses a fresh `ledger-task2-verified-regression-<GUID>` basetemp:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase5_engine.py tests/test_phase51_backtest_controls.py tests/test_phase5_context.py tests/test_phase52_saved_runs_and_chart_series.py tests/test_phase54_validation_and_management.py tests/test_phase55_research_and_replay.py tests/test_phase56_replay_workspace.py tests/test_phase561_replay_consistency.py tests/test_phase63_journal_research.py::test_xau_baseline_v11_identity_and_structure_parameters_are_stable -q -p no:cacheprovider --basetemp $taskTemp --tb=short
```

The existing dedicated Gold regression checks frozen identity/structure defaults;
it is not a comprehensive proof of every Gold trading path. Existing tests were
not rewritten. The full suite also reruns Task 1 broker, import-order, Journal
and migration/preservation checks.

Frontend commands from `frontend`:

```powershell
npm.cmd run build -- --outDir C:\Users\jamie\AppData\Local\Temp\ledger-task2-verified-build-9af1b4938483493db354f1f706c72c7b
node --test tests/journal.test.js
```

Final production JS: 678.39 kB / 198.02 kB gzip; CSS: 39.69 kB / 8.40 kB gzip.
The pre-existing Vite >500 kB chunk warning remains. Backend warnings are the
existing Starlette/httpx TestClient and AnyIO BlockingPortal deprecations.

During development, two initial fixture assertions were corrected to match the
existing `target` exit-reason name and to include the previous-close gap in the
hand-calculated true range. No strategy threshold was tuned. An initial full
pytest invocation hit permissions on the default `pytest-of-jamie` temp directory
(118 passed, 64 fixture setup errors); rerunning with fresh isolated basetemp
resolved this environment issue. No unresolved test/build failure remains.

Final no-lookahead review corrected base selection: it now fixes the longest
depth/contraction-qualified base before comparing the breakout close. The exact
regression `test_base_selection_is_fixed_before_observing_breakout_close` proves
that a preselected pivot of 102 and a close of 101 cannot fall back to a shorter
base with pivot 100. A later close above 102 uses the original 102 pivot.
The 45-test strategy suite and all final checks above ran after this correction.

Browser checks used existing isolated headless Chrome and a local synthetic
provider with outbound HTTP disabled, separate temp DB/uploads and no credentials.
Checked registry selection/daily controls, valid filled setup, rejected chase,
saved-run reopening, warning persistence, Trade Audit levels/markers, and 1024px
overflow. The final rebuilt UI was reloaded and its actual audit canvases checked.
Charts were visually inspected. These browser checks used the final frontend;
the subsequent base-selection backend correction was verified by the final
strategy/full/regression suites, without another browser run. Browser results are synthetic integration checks,
not a live Alpaca/OANDA validation. Known pre-existing Replay reveal risks remain
explicitly deferred as documented in the Task 1 report.

## 8. Manual acceptance

1. In Backtest choose **Momentum / VCP Breakout · baseline v1.0**; use one US
   stock ticker, daily timeframe, auto/regular session and overnight enabled.
2. Choose a multi-year range with at least 250 prior observations inside it.
   Keep the documented defaults for the baseline; set realistic existing cost
   and risk controls explicitly. Use the configured Alpaca data path.
3. Run and inspect Detected breakout setups. Confirm pivot/base boundaries,
   prior-volume benchmark, confirmed structural stop and entry/rejection reason.
4. For a fill, verify next-session open, unchanged initial stop and target
   E+2*(E-stop). Open Trade Audit and inspect the base, pivot, breakout and exit.
5. Open the saved result from Runs without rerunning. Check parameters, setup
   outcomes and survivorship warning remain present.
6. For an explicit multi-stock test, review alphabetical candidate ordering,
   position/exposure limits and chosen tickers before interpreting portfolio metrics.
   Do not label these as historical-universe performance.
7. Use development/validation/out-of-sample windows with adequate warm-up;
   do not select defaults based on the greenest result. Future exit/filter changes
   require separate variants, one variable at a time.

## 9. Known-in-advance examples

Synthetic valid fixture: 30-session base high/pivot 100, low 92 (8% depth),
last confirmed swing low 97.5 on January 2, 2024. Friday January 5 close 101,
volume 1.2m versus prior average 875k. Recent/early ATR% ratio about 0.1932;
volume contraction ratio 0.5; average dollar volume $85.875m. Monday January 8
open 101 enters; risk/share 3.5, target 108. Tuesday January 9 hits 108:
exactly +2R with zero configured costs. All date/price/exit/R expectations are
asserted in the hand-worked test.

Rejected example: same confirmed setup but next open 103 (3% above pivot),
so `entry_too_extended`, no trade and the original pivot remains 100. Opens
99 or 100 reject as `open_not_above_pivot`. Required risk above the configured
cap rejects as `stop_distance_exceeded`; the stop is never replaced.

## 10. Recommended next phase

Individual-symbol logic and the existing explicit-list portfolio runner are
available. Before universe-wide historical research, add and validate a versioned
point-in-time security master, exchange calendar, ticker/corporate-action and
delisting treatment. Then specify universe eligibility, ranking/tie-breaks and
missing-session policies explicitly, reusing the existing engine's capital,
concurrency and execution controls. No fake point-in-time universe or new
portfolio model is hidden in this baseline.
