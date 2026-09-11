# Ledger v2 data sources — Phase 6.2

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

Continuous futures may additionally carry `source_contract`. `MarketStore` now preserves that provenance field.

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

This first rule is intentionally not labelled TradingView-equivalent. The next futures-data refinement should calculate and persist volume-crossover roll dates, then version/cache that roll schedule.

Intraday Replay aggregation uses an 18:00 America/New_York futures-session anchor and does not discard overnight data through the US-equity session filter.

## SEC EDGAR / FRED

Unchanged from earlier phases: SEC remains the filing/fundamentals source and FRED remains the macro source.

## Next data work

- futures product metadata: tick size, point value, contract multiplier, expiry;
- CME RTH/ETH session profiles in the UI and backtest engine;
- volume-derived continuous-contract roll schedules;
- provider-history capability metadata so the UI can communicate plan/history limits;
- cursor/range-based historical pagination for Charts instead of growing a whole lookback window;
- optional GC1!/MNQ1!/MGC1! aliases once the NQ1! path has been validated.
