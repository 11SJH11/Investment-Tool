# Ledger v2 data sources — Phase 3

## Alpaca

Used for the active US-equity security master, historical OHLCV and latest market snapshots.

Ledger keeps historical and latest data provenance explicit:

```text
Historical: configured SIP feed, split adjusted
Latest:     configured free/live feed (IEX in the current setup)
```

The screener's **Refresh prices** operation uses Alpaca's multi-symbol latest-bar endpoint in chunks and stores one price snapshot per symbol in SQLite. Scans themselves do not call Alpaca.

Research OHLCV goes through `MarketDataService`, which reuses Phase 2 Parquet cache coverage.

## SEC EDGAR

Used for ticker/CIK mapping and filing-derived fundamentals.

Phase 3 adds the SEC nightly bulk Company Facts archive:

```text
https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip
```

The file is streamed to `backend/data/sec/companyfacts.zip` to avoid holding the whole archive in memory. Ledger parses only companies whose CIK is present in the locally cached security universe and persists normalized screener metrics in SQLite.

Current normalized values include revenue, YoY revenue growth, net income, margins, assets, liabilities, equity, cash, operating cash flow, capex, free cash flow, diluted EPS, shares outstanding and ROE where the filing tags are available.

## FRED

Unchanged from Phase 2. FRED remains the macro provider for later Dashboard/Markets work.

## Derived valuation values

Phase 3 intentionally distinguishes raw provider values from locally derived metrics:

- market cap = SEC shares outstanding × latest stored Alpaca price
- P/E (FY) = latest stored Alpaca price ÷ SEC diluted fiscal-year EPS

These can be improved later (for example, TTM EPS) without changing the screener API/storage boundaries.
