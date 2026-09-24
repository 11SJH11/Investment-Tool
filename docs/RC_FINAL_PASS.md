# Final RC workflow / UX pass

This is the last planned broad workflow/UI change before user-led testing. After this point, normal development should be limited to defects discovered in use and genuinely separate add-ons.

## Foundation retained

- Backtest engine, strategy implementations, Replay causality/no-lookahead rules, continuous-futures execution rules and broker accounting semantics were not redesigned in this pass.
- Previous RC work remains included: denser UI, viewport-sized Charts/Replay, 20-row table defaults, removable finished Backtest jobs, cached/background Screener maintenance and the synthetic demo database.
- Demo data remains isolated in `data/demo/ledger.db` and is never selected automatically.

## Journal and Analysis

- Trades use the shared table for search/filtering; the redundant Journal filter strip was removed.
- Broker connection management lives in Settings rather than taking space in Journal/Portfolio.
- Fixed-enum/result cells use restrained semantic styling for faster scanning (wins/losses, source/mode, grades and plan adherence where applicable).
- Manual entry now continues into the review workflow rather than presenting review metadata as part of execution capture.
- Reusable review values are creatable/selectable: saved custom setups, conditions, emotions, mistakes, confluences and similar fields become later suggestions. Freeform narrative fields remain freeform.
- Analysis supports up to four simultaneous descriptive dimensions so a sample can be inspected as combinations such as strategy + session + entry-time bucket + emotion.
- Breakdown results can be ordered by sample size, expectancy, win rate, total R or label. Individual categorical charts can also be sorted best/worst/sample-size while time-ordered charts retain their natural order.
- Dense time-series charts avoid rendering a marker for every trade once the sample is large.
- Calendar reuses the already-loaded Journal report instead of making a second duplicate monthly aggregation request.

## Charts and Replay

- Drawings continue to persist in market-space timestamps and prices.
- Cross-timeframe off-grid anchors no longer send fractional logical indexes directly to Lightweight Charts. They resolve through the surrounding valid integer bar coordinates and interpolate in pixel space. This prevents a 1m anchor from collapsing to the chart's left edge when viewed on 5m/15m/1h.
- Whole-object drags move through logical bar space, so session/weekend gaps do not create large wall-clock jumps.
- Timeframe changes do not rewrite the stored drawing anchors.
- Replay Next/Previous/+5 operate relative to the selected timeframe while every intervening canonical 1m source bar is still evaluated for fills/stops/targets.
- Replay timeframe controls are visible both normally and in full screen. The redundant `Current` control was removed.

## Backtest workflow

- Run name is required and defaults to `Run N`, where N is one more than the highest saved run id. The user may freely replace it.
- Tags remain optional next to the name. Notes remain optional lower in the configuration.
- The normal symbol input accepts multiple comma/space/semicolon-separated symbols, replacing the redundant secondary multi-symbol section.
- Execution, costs/slippage, account limits, trading schedule and session guardrails live under one compact `Advanced` disclosure.
- Research role is no longer normal UI; ordinary runs keep the internal development role and validation/OOS workflows continue to assign their explicit roles.
- Strategy-owned risk-management information is reference material near the bottom rather than primary configuration.
- `Ready to run` remains the final run summary.
- Saved results now open into a dedicated `Run Viewer` rather than appearing beneath the configuration form. Run Viewer has Summary, Trades and Analysis views plus `Use settings` and `Back to Runs` actions.

## Screener / large-data behaviour

- Shared DataTable shows 20 rows by default and can expand to 100 rows per page.
- Screener returns the last persistent snapshot immediately while background maintenance runs; stale rows remain visible during refresh.
- Startup maintenance refreshes technicals from local cached daily bars when stale and can batch-refresh Alpaca price snapshots when configured. SEC bulk fundamentals remain manual because of their size.
- Background maintenance is throttled across restarts and disabled for the synthetic demo database.

## Demo dataset

The deterministic synthetic database represents roughly three years of realistic UI load and contains approximately:

- 1,211 Journal trades
- 553 Daily Reviews
- 4 Playbooks
- 90 saved Backtest runs
- 96 portfolio transactions
- 160 research items
- 300 Screener securities with populated market/fundamental/technical data

All demo records are synthetic and must not be used to draw investment or strategy-performance conclusions. See `data/demo/README.md` for the temporary data-directory setting.

## Release posture

This RC is intended for full manual/usability testing. New work after that should normally be one of:

1. a reproducible bug fix;
2. a small usability correction revealed by real use; or
3. a separately scoped add-on that does not destabilise the core workflow.

The final automated verification record is in `docs/FINAL_RC_VERIFICATION.md`.
