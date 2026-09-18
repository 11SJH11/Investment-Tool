# Checkpoint 8.1: continuous futures research

Reviewed official documentation on 2026-09-18. Research findings, not a claim of
implemented TradingView parity. This research preceded implementation; current
Ledger selection/adjustment is documented in RELEASE_CHECKPOINT_8.md.

## TradingView methodology

- A continuous symbol links dated contracts. TradingView describes a per-symbol
  switching rule informed by historical volume crossover patterns, applied
  throughout history. It does **not** describe a universal rule that switches
  immediately whenever next-contract live volume becomes greater. Its example
  business-day offset is illustrative, not a published NQ rule. No exact NQ
  offset was established from this page.
  [Official switching methodology](https://www.tradingview.com/support/solutions/43000691027-how-is-the-switching-date-of-contracts-determined-in-continuous-futures/)
- Back-adjustment is optional and disabled by default. Historical segments are
  shifted using the difference between the two contracts' closes on the nearby
  daily bar, generally the day before switching. Ledger's current previous-close
  to next-open observed-gap adjustment is a different methodology.
  [Official back-adjustment description](https://www.tradingview.com/support/solutions/43000685266-how-can-i-enable-backadjustment-for-continuous-futures/)
- Where supported for CME/EUREX, trading 1! routes to the currently included
  dated contract. A continuous chart is not itself a deliverable contract; 2!
  does not have that trading support. Ledger must preserve the dated execution
  identity separately from the selected continuous alias.
  [Official continuous-contract trading](https://www.tradingview.com/support/solutions/43000690938-can-i-trade-a-continuous-futures-contract-e-g-es1-es2/)
- Switching markers expose date and contract transition information.
  [Official switching markers](https://www.tradingview.com/support/solutions/43000689313-switching-continuous-futures-contracts/)
- TradingView distinguishes CME electronic sessions and regular hours. Its
  documented regular session is 08:30–15:15 Chicago time. Ledger's ORB strategy
  study window must not be mistaken for a complete exchange session definition.
  [Official session distinction](https://www.tradingview.com/support/solutions/43000670909-regular-and-electronic-trading-hours-for-cme-futures/)

Massive describes exchange-session dates separately from timestamps; use its
contract specifications and session data, not fabricated expiry/session bars.
[Official futures overview](https://massive.com/docs/rest/futures/overview)

## Implementation requirements recorded before coding

1. Establish a deterministic, versioned schedule for each supported family. Keep
   authoritative observed roll dates/rule evidence separate from an explicitly
   named approximation. Do not invent a TradingView NQ offset. A causal prior
   completed-session volume rule, if chosen, must be labelled as Ledger's own
   policy rather than equivalent to TradingView's historical per-symbol rule.
2. Preserve continuous_alias, source_contract, roll_schedule_version,
   adjustment_mode and provider through cache, aggregation, Replay and Backtest.
   Existing provenance covers only some of these fields.
3. Keep adjusted context separate from raw dated fills. Resolve dated economics
   and whole-contract quantity at execution; persist both displayed/executed IDs.
4. Reject an open position crossing a roll; cancel/reject old-contract pending
   orders explicitly. Keep flat intraday transitions valid. Do not create a fill
   from two different contracts or weaken revealed-minute Replay causality.
5. Add NQ1! Backtest/Replay tests and browser checks before enabling alias execution.

## Parity validation procedure (not yet performed)

For several actual NQ quarterly transitions, record the from/to contracts and
switching timestamp from TradingView's contract markers. Export licensed/user-
provided CME_MINI:NQ1! data covering five trading sessions before and after each
transition, including the roll session. Record export time, timezone, feed delay,
session selection, adjustment toggle and 1m/5m/15m/1h resolution.

Export Ledger's corresponding bars including source contract, schedule version,
provider and adjustment mode. Normalize timestamps to UTC and compare matching
bar-start semantics before comparing OHLCV. Compare raw with raw, adjusted with
adjusted; preserve missing timestamps as missing. Inspect roll boundary separately
from price/volume differences. Record maximum absolute OHLC differences, volume
differences, missing bars, contract mismatches and reasons supported by evidence.
Never shift prices, timestamps or roll dates just to make comparisons pass.

The offline implementation is `backend/tools/compare_continuous.py`; run from
backend with `.venv/Scripts/python.exe tools/compare_continuous.py ledger.csv reference.csv`.
CSV headers: timestamp, open, high, low, close, volume; optional source_contract.
Timestamps must include UTC offsets. Export/rename headers explicitly; the tool
does not guess units, align prices or fill missing bars. It reports timestamp
coverage, maximum OHLCV differences, optional contract mismatches and roll lists.

No licensed TradingView export or actual roll-period comparison was supplied or
performed. Provider trade coverage, settlement-vs-trade close, session definitions,
roll timing and adjustment anchoring are possible discrepancy sources, not
established explanations for unmeasured discrepancies. Exact parity is unverified.
