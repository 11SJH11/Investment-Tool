# Checkpoint 8.1: continuous futures research

Reviewed official documentation on 2026-09-18. Research findings, not a claim of
implemented TradingView parity. This research preceded implementation; current
Ledger selection/adjustment is documented in this document.

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

## Methodology and execution

Default schedule: `prior-session-volume45-v1`, generic across the twelve registered
families. Adjacent contracts are ordered by provider last-trade date. In the 45
calendar days before the front expiry, compare matching session-date volumes.
The first strictly greater next-contract volume qualifies. Missing sessions are
not zero; ties do not qualify. A session is conservatively complete at the later
of its start + 24 hours and 18:00 New York on its provider session-end date.
Switch at the first subsequent observed next-contract session start at/after that
boundary. That new session's OHLCV does not participate in the decision. Do not
switch back. No observed crossover uses `expiry-fallback` at UTC midnight after
the provider last-trade date. Nonchronological transitions are rejected instead
of overlapping two source contracts.

This volume-window rule and expiry fallback are **Ledger approximations**. They
are not TradingView's undisclosed per-symbol historical switching rule. In
particular, adjacent listed monthly commodity contracts are not necessarily the
same active-month sequence used by another vendor. There is no settlement-time,
delivery, first-notice or broker-margin model. Exact root-specific alignment is
a future evidence-driven refinement, with a new schedule version when rules change.

Reference/schedule records share the durable metadata database under distinct
versioned keys. Pair keys include contract reference dates; developing schedules
use an hourly key, historical pairs use a final key. Existing cache TTL/cooldown
and process-wide single flight apply. Explicit refresh updates schedule evidence.
Provider daily evidence is fetched once per cached pair, independent of displayed
timeframe. There can be two daily aggregate requests per uncached pair; these are
separate from the already cached contract-discovery request.

Raw dated OHLCV remains in the shared MarketDataService cache. Continuous history
is reconstructed against the schedule on retrieval, rather than persisting stale
alias bars selected before delayed roll evidence became available. A regression
covers evidence changing from expiry fallback to an earlier observed crossover.
Existing caches are retained; provenance-v3 uses a separate namespace.

Each continuous bar retains alias, source contract, schedule version, provider,
adjustment mode/method/offset, effective roll time and last-trade date. Aggregation
groups by source contract, so a bar cannot blend two contracts. Chart/Replay
disclosures show the current contract and revealed/loaded transition list without
altering chart drawing infrastructure.

`FUTURES_BACK_ADJUST=false` remains the default. Adjusted charts add cumulative
new-close minus old-close differences to older segments, using the latest common
completed daily session at/before each actual switch. Missing common closes reject
adjustment; adjacent intraday price gaps are not substituted. Older prices depend
on later rolls in the requested range, so adjusted data is chart context, not
causal execution data. Raw execution uses a provider copy and a separate raw cache;
the shared chart setting is never mutated.

Backtest/Replay front aliases resolve raw same-family dated contracts from valid
bar provenance. No provenance, adjusted prices or wrong-family sources fail
explicitly. Tick size, USD point value, full-notional constraints and whole-contract
sizing use the existing generic economics. Strategy rules/fills/cost policies are
unchanged. A $10,000 account does not gain invented NQ margin leverage.

An open position reaching a different source contract rejects the Backtest run
before marking or filling against the new contract. Replay terminates before a
cross-roll fill, retains the last processed frontier, marks integrity compromised
and requires a fresh session. Pending entries cancel at a roll. Flat sessions can
continue. Journal stores displayed_symbol and executed_contract in source_metadata
and calculates P&L using the dated multiplier; existing IDs/notes remain intact.

## TradingView comparison

Official references and exact differences are in CONTINUOUS_FUTURES_RESEARCH.md.
The offline tool `backend/tools/compare_continuous.py` compares timestamp-matched
OHLCV, missing bars, optional source IDs and transition lists. Use separate 1m,
5m, 15m and 1h exports covering five trading days either side of several actual
NQ roll markers. Keep session, timezone, price adjustment and feed entitlement
matched. Do not fill missing data or shift prices to manufacture agreement.
Real exports were not available: no measured vendor discrepancies or equivalence
are claimed. Daily-close adjustment follows the documented concept, but identical
roll timestamps/data/close selection have not been demonstrated.


## NQ1! diagnosis and remedy

Official references: [Massive contract reference](https://massive.com/docs/rest/futures/contracts), [futures aggregates](https://massive.com/docs/rest/futures/aggregates), and [futures plans](https://massive.com/futures).

The contracts endpoint without `date` returns historical daily snapshots, not a unique contract directory. A real NQ request returned 1,000 rows, repeated NQH5 records and another page. Adding a point-in-time date and `type=single` returned 13 unique contracts in one page. The previous implementation paginated the wrong dataset and exhausted the reference budget.

Discovery now requests dated monthly snapshots spanning the requested range, deduplicates contracts, and persists them separately from OHLCV. A new cache namespace avoids reusing the earlier erroneous lookup/cooldown. Every date/expiry comes from Massive; no synthetic contract calendar or bars are introduced. All Massive endpoint calls share a per-key process budget, default five requests/minute, plus bounded Retry-After recovery. Set MASSIVE_CALLS_PER_MINUTE only to a rate supported by your subscription. Long historical cold loads still take time on restricted plans. Other applications using the same key can consume its quota.

Massive remains the selected provider. The real access tested was sufficient; no provider switch was necessary. If entitlement later proves insufficient, Databento's CME historical data and continuous-symbol mapping is a documented alternative requiring a separate integration, subscription and comparison. No automatic fallback or claim of equal data has been added.

Real read-only checks used isolated data/cache directories, never the user's Ledger database:
- September 1, 2026: 1m/5m/15m/1h bars, source NQU6. ORB produced two raw dated-contract fills with $1,000,000 test capital and one-contract sizing. Engine economics remain tick .25, tick value $5, point value $20.
- September 18, 2026: 1,150 / 231 / 77 / 20 bars at the respective timeframes, source NQZ6.
- September 10–18: old contract NQU6, transition at the September 15 evening session boundary, new NQZ6 thereafter. UTC dates can contain both contracts around an evening session boundary.
- Browser Charts loaded all four timeframes from exported real provider frames. Browser Replay placed and manually closed a simulated NQ trade; Journal retained NQ1!, NQU6, raw adjustment and roll-version metadata.
- Frozen roll guards continue to reject open-position transfer and cancel stale pending orders; no artificial roll-gap P&L is introduced.

TradingView CME_MINI:NQ1! parity remains unverified: no comparable export was provided. Existing roll/source provenance and comparison workflow remain available. No claim covers every date, provider outage, entitlement or live quote stream.
