# Verification

Run `powershell -ExecutionPolicy Bypass -File ./Verify-Ledger.ps1` from the repository
root after installing `backend/requirements-dev.txt` and frontend dependencies.
The execution-policy switch applies to this verification process only.

It runs the full backend suite, frontend utility tests and production build,
failing on the first unsuccessful phase. Tests disable dotenv parsing and use
temporary databases. Python bytecode output is disabled. The production build
also disables dotenv reading and writes outside the repository. It does not
restart Ledger, alter installed dependencies, or access the live database.
Optional `-OutputDirectory` must be outside the repository. The artifact path
is printed for isolated browser checks. Run `git diff --check` before committing.

Browser scripts under `frontend/tests/browser` are opt-in and require an isolated
browser profile/server. Never aim fixtures at the live application database.

## Continuous-futures warm-cache contract

While source/reference evidence remains valid, identical covered requests return
identical OHLCV/source-contract provenance with zero additional provider calls.
The first derived Parquet read after cold construction or restart may read disk.
Subsequent in-memory hits avoid physical Parquet reads. Memory expiry/eviction
is not a reason to redownload durable history. Reference expiry or explicit
refresh can legitimately require provider validation.

Tests cover cold/warm equality, provider-call counts, a memory hit, cleared-memory
new-service reconstruction and isolation from caller mutation.


## Manual regression checklist

Use isolated fixture storage and browser profiles; never replace the user database.

1. Draw/drag rectangle, trend and fib anchors on 1m; switch 5m/15m/1h/back and
   confirm market anchors persist, including off-grid and cross-session points.
2. Replay each timeframe: Next/Previous/+5, fill a market order, close next-open,
   verify Journal idempotency, then Stay/save/leave/resume. Simulate unavailable
   storage/history and confirm no false checkpoint-success message.
3. Journal: create/review a manual trade, save a reusable custom option, combine
   two to four Analysis dimensions, verify N and separate currency totals.
4. Calendar: change months and open a busy date; inspect its Daily Review.
5. Backtest: queue multiple symbols, inspect default Run N, configure another
   while running, open Summary/Trades/Analysis, cancel and clear finished jobs;
   immutable saved Runs must remain intact. Test concurrent research CPU limits.
6. Screener: cached results remain visible while refresh completes. Portfolio
   updates its local snapshot after backend broker sync; connection setup stays
   in Settings. Strategies can navigate to Indicators and back.
7. Check 1024/1440/1920 widths for internal table scroll, no page overflow or
   runtime errors. Review provider-path NQ separately when entitlement permits;
   mocked tests do not establish live data availability or TradingView parity.

Current automated results and the exact measured 5x5 parity comparison are in
[Reliability acceptance](RELIABILITY_ACCEPTANCE.md). Historical Linux/native-binding
failures in removed RC notes are superseded by verified Windows production builds;
reinstalling working dependencies is not a verification step.
