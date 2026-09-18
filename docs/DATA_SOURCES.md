# Ledger current data sources

## Shared routing

All OHLCV consumers now enter through `MarketDataService`, which resolves the instrument and provider before consulting the provider-specific cache namespace.

```text
US equities -> Alpaca
XAUUSD      -> OANDA XAU_USD
NQ1!        -> Massive Futures + Ledger continuous-contract construction
```

The canonical bar columns remain:

```text
timestamp, open, high, low, close, volume
```

Futures bars retain source_contract, roll_method, roll_schedule_version, roll_effective_at, adjustment_method and adjustment_offset through cache/aggregation. Provider routing and cache namespaces remain explicit.

## Alpaca

Unchanged for the active US-equity security master, historical OHLCV and latest market snapshots. Equity session filtering remains New York regular (09:30–16:00) or extended (04:00–20:00).

## OANDA — XAUUSD

Ledger's `XAUUSD` alias maps to OANDA `XAU_USD` midpoint candles. The candle endpoint needs the access token but not an account ID. Incomplete current candles are excluded from the deterministic historical path.

OANDA volume is candle activity/tick volume; it should not be interpreted as COMEX contract volume.

Intraday Replay aggregation uses a 17:00 America/New_York session anchor.

## Massive Futures — NQ1!

Massive supplies dated futures contracts and OHLCV aggregates. Phase 6.2 accepts dated futures-like symbols in the backend and advertises `NQ1!` in SymbolSearch.

### Continuous contract v1

`NQ1!` currently uses a calendar-front rule: choose the nearest NQ contract whose last-trade date has not passed, fetch each required dated contract, and concatenate the resulting segments. `source_contract` is retained on every bar.

`FUTURES_BACK_ADJUST=false` is the default. When enabled, Ledger applies backward additive gap adjustment across contract switches.

This first rule is intentionally not labelled TradingView-equivalent. The next futures-data refinement must use an explicit versioned schedule. TradingView documents per-symbol rules informed by historical volume patterns, not a universal immediate volume-crossover rule; see CONTINUOUS_FUTURES_RESEARCH.md.

Intraday Replay aggregation uses an 18:00 America/New_York futures-session anchor and does not discard overnight data through the US-equity session filter.

## SEC EDGAR / FRED

Unchanged from earlier phases: SEC remains the filing/fundamentals source and FRED remains the macro source.

## Current execution scope and remaining work

Twelve verified contract families already carry tick size, point value, multiplier
and whole-contract sizing: NQ/MNQ, ES/MES, YM/MYM, RTY/M2K, GC/MGC and CL/MCL.
All have continuous chart aliases. Dated contracts support Backtest and Replay;
continuous execution is blocked pending the explicitly authorized checkpoint 8.
Full-notional limits are used, not a broker futures margin model. Back-adjusted
history is chart-only and must never become an execution fill.

Checkpoint 8's first save point adds durable contract-reference caching (24-hour
TTL, bounded 429 stale fallback/cooldown, process-wide single flight). Verified/
versioned roll schedules, raw dated execution behind continuous aliases and roll-
boundary diagnostics remain outstanding. No TradingView equivalence is claimed.
Provider entitlement/history coverage still requires real-market acceptance.

## Broker histories and unsupported data

OANDA closed-history imports feed the common Journal, read-only and idempotent.
Trading 212 account/position snapshots and history feed Portfolio separately from
manual transaction accounting. Both support provider/account/environment profiles.
Tradovate remains unsupported; Autochartist remains scaffold-only with no network.
No verified DXY feed or point-in-time historical equity universe is available.
Historical universe may contain survivorship bias. Equity price/volume baselines
must not be represented as point-in-time fundamental or portfolio research.
