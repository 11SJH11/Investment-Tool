# Gold Asia 15m IFVG — controlled loss-reduction tests

This package supplies **one new plugin file with six separately selectable strategies**. The original `gold_asia_15m_ifvg_research_v1.py` stays exactly as it is. The objective is to test whether we can remove full-stop losses or reduce their severity **without losing more winning expectancy**.

> **Status:** Research-only Python variants. Syntax and isolated smoke checks can be performed here, but the files **have not been executed against your live Ledger checkout/cache**. Confirm your local plugin API accepts them by using **Refresh strategies** and completing a smoke run. Neither historical results nor broker realism are guaranteed.

## Install (original Ledger checkout, not the isolated Codex worktree)

1. Extract `gold_ifvg_loss_reduction_tests.zip`.
2. Copy **only** `gold_asia_15m_ifvg_loss_tests_v2.py` into:
   `C:\Users\jamie\Project\Investment-Tool\backend\app\backtesting\strategies\`
3. Make sure the existing `gold_asia_15m_ifvg_research_v1.py` is already in that folder.
4. In Ledger select **Strategies → Refresh strategies** (when no jobs are active).
5. Six new `Gold IFVG V2` entries should appear in Backtest → Strategy.
6. If Refresh reports an error, **do not replace/edit the original V1**; share the exact error.

Do **not** put the pack's README or CSV files into the strategies folder (only the `.py` file).

## Frozen settings for every first-pass development test

These replicate Run 209 exactly **except for the strategy selected**.

| Ledger field | Enter/select |
|---|---|
| Symbol | `XAUUSD` |
| Primary timeframe | `1m` |
| Additional timeframes | Leave empty — each strategy declares `15m` internally |
| Date from | `2026-03-01` |
| Date to | `2026-10-17` |
| Market data session | `Auto · match instrument` (`auto`, resolves to `24h`) |
| Strategy parameter — Direction | `both` |
| Starting balance | `10000` (USD) |
| Position sizing | `Risk per trade (%)` (`risk_pct`) |
| Risk per trade | `1` (%) |
| Maximum leverage | `20` |
| Maximum open positions | `5` |
| Commission per order | `0` |
| Spread (bps) | `0` |
| Slippage (bps) | `0` |
| Same-bar stop/target | `Stop first` |
| Allow overnight | `Yes` |
| Trading weekdays | **Monday, Tuesday, Wednesday, Thursday, Friday** (`0,1,2,3,4`) |
| Entry windows | Leave empty |
| Force-close time | Leave empty |
| Max trades per day | Empty / disabled |
| Daily loss stop (R) | Empty / disabled |
| Consecutive loss stop | Empty / disabled |
| Cooldown minutes | `0` |
| Save run | `Yes` |
| Run test role | `development` |
| Parameter sweep | **Off** for these first tests |

**Why keep Monday–Friday?** Run 209 excluded Sunday. Mixing weekday settings would make a comparison invalid. Once Sunday support is fixed, create a NEW full baseline and rerun all variants on the same expanded weekdays. **Why zero costs?** First isolate strategy-rule changes, then do explicit cost-stress reruns; frictionless results are NOT broker-realistic.

## Exact test order

All development tests use the settings above. Only change **Strategy** and **Run name** as shown.

| ID | Strategy dropdown/key | Run name | One change |
|---|---|---|---|
| T00 | `gold_asia_15m_ifvg_research_v1` | `GOLD-V1-REPRO-2026` | Baseline comparison / re-run if needed |
| T01 | `gold_ifvg_v2_skip_23et` | `GOLD-T01-NO-23ET` | Reject first IFVG confirmed 23:00–23:59 NY |
| T02 | `gold_ifvg_v2_fvg_ratio_020` | `GOLD-T02-FVG-RATIO-020` | Reject FVG-size / signal-time stop distance above 0.20 |
| T03 | `gold_ifvg_v2_be_050` | `GOLD-T03-BE-050` | Breakeven after +0.50R, next bar |
| T04 | `gold_ifvg_v2_be_080` | `GOLD-T04-BE-080` | Breakeven after +0.80R, next bar |
| T05 | `gold_ifvg_v2_no_be` | `GOLD-T05-NO-BE` | No breakeven adjustment |
| T06 | `gold_ifvg_v2_reclaim_exit` | `GOLD-T06-EARLY-15M-EXIT` | Exit next 1m open on 15m close back through inverted FVG boundary |

**Notes:** T01/T02 remove entry signals, consuming that session's first IFVG rather than replacing it with a later one. T02 uses the **last completed 1m close at signal time**, not the future opening fill, to avoid lookahead. Consequently the threshold is not exactly the same metric as in retrospective trade CSV analysis. T03–T06 can change exits, overlapping positions and later signal availability, so compare actual results, not simple subtraction from V1 outcomes.

### Phase 2: explicit cost stress, not new strategy rules

Only once the above is complete:

- **T07:** Rerun **V1**, same dates/settings but `Spread = 2` bps and `Slippage = 0.5` bps, `Commission = 0`. Name `GOLD-T07-V1-COST-STRESS`.
- **T08:** Rerun **one selected V2**, exactly the same cost stress. Name `GOLD-T08-CHILD-COST-STRESS`. The `2/0.5` values are **hypothetical sensitivity assumptions, not measured TradeQuo costs**. Later use validated MT5 bid/ask, slippage and actual broker lot/contract specifications.
- **T11 (optional money management test):** Rerun selected V2 with `Risk per trade = 0.5` (%) instead of 1; leave strategy untouched. This lowers both wins and losses in cash and is **not evidence of a better signal**.

### Phase 3: separate-period check

**Do not use 2025 results to pick the rules.** After choosing at most one variant on the 2026 development window, run **both** V1 and that frozen variant on `2025-01-01` through `2025-12-31`, identical other settings. Name `GOLD-T09-V1-2025` and `GOLD-T10-CHILD-2025`. The 2025 period is a separate evaluation period, **not guaranteed pristine holdout** if previously viewed or optimized against. Save any genuinely unseen/forward period for final validation.

### What to send back after the first seven runs

Download from each run:

- Summary JSON
- All trades CSV

Record result ID, # trades, wins, losses, BE, total R, net P&L, PF, max drawdown and source/data fingerprints in `RESULTS_TO_FILL.csv`. The **number of baseline winners lost**, **baseline losers removed**, **new trades added** and **changes in exit outcomes** matter more than a single improved profit factor.

Compare two trade CSVs from PowerShell:

```powershell
python .\compare_gold_ifvg_trades.py "C:\path\run-209-trades.csv" "C:\path\your-v2-trades.csv" --out ".\comparison.csv"
```

Use full exported trade CSVs, not truncated pages. It matches by IFVG confirmation time, NY Asia session, direction and symbol.

### Go / no-go rules

1. First verify T00 reproduces 83 trades, +19R with equivalent data, session and strategy source. A mismatch must be investigated before attributing improvements to variants.
2. Don't prefer a filter if it removes a large fraction of the 45 original winners even when total R rises in-sample.
3. Evaluate **net expectancy, drawdown, trades/month, loss reduction, and cost sensitivity** together.
4. A small positive 2026 improvement may be chance. Do not optimize thresholds repeatedly on the same 83 trades.
5. No candidate is live-trading-ready until execution model, MT5 contract volume steps, spread/slippage and forward-demo evidence are verified.

### Run 209 baseline reference

From your uploaded summary: 83 trades, 45 winners, 26 losers, 12 breakeven, +19R, $2,049.72 net P&L, 1.73 PF(R), −5.13% max drawdown, on USD $10,000 and **zero costs**. It is a research baseline, not evidence of a proven live edge.
