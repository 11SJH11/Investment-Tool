# Checkpoint 8 — first verified save point

2026-09-18. Based on checkpoint 7 commit `5637306`. **Checkpoint 8 is not complete.**
This is a bounded save point under the user's staged-work instruction. Resume
8.2–8.7 next; do not redo completed checkpoints 1–7 or claim NQ1! execution support.

## Completed here

- 8.1 official TradingView research: CONTINUOUS_FUTURES_RESEARCH.md includes
  switching, adjustment, dated execution, references and a parity-check procedure.
- 8.8 durable Massive contract-reference cache and rate-limit protection.
- 8B Trading 212 Portfolio investor metrics and explicit unavailable values.
- 8C broker foundation audit and two independent provider-contract tests. Shared
  Journal storage supports extensions; dispatch/registration still needs a small
  provider-specific integration change. See BROKER_EXTENSION_CONTRACT.md.

## Exact changed files

- backend/app/data/http.py
- backend/app/data/providers/massive_futures.py
- backend/app/services/container.py
- backend/app/services/market_data.py
- frontend/src/features/portfolio/BrokerPortfolioPanel.jsx
- frontend/src/features/portfolio/PortfolioPage.jsx
- docs/DATA_SOURCES.md
- docs/RELEASE_CHECKPOINTS.md

## Exact new files

- backend/app/data/contract_reference_cache.py
- backend/tests/test_massive_reference_cache.py
- backend/tests/test_broker_extension_contract.py
- frontend/src/features/portfolio/brokerPortfolioUtils.js
- frontend/tests/brokerPortfolio.test.js
- docs/CONTINUOUS_FUTURES_RESEARCH.md
- docs/BROKER_EXTENSION_CONTRACT.md
- docs/RELEASE_CHECKPOINT_8_PART_1.md

## Data and cache behaviour

No application/Journal database migration. No user data or credentials were used
or modified. Runtime adds a separate `contract-reference.sqlite` under configured
market_data_dir, with `contract_reference(key,payload,fetched,retry_until)`. Creation
is idempotent. Only normalized contract symbols/product codes/trading dates are
stored; authentication headers are not cached. OHLCV remains in its existing cache.

Reference TTL is 24 hours. Stale metadata up to 30 days old can be reused on 429;
older/missing metadata produces a clear rate-limit error. Such metadata does not
invent a missing next contract: existing overlap selection can still reject an
uncovered period. Explicit market-data force_refresh refreshes references once;
refresh=false reuses fresh metadata. Failed/incomplete pagination is not cached.

Contract pagination stays on the same allowed endpoint/host, rejects loops and
stops after 100 pages. Header authentication is retained. HTTP GET retries remain
bounded to three attempts; numeric and HTTP-date Retry-After are supported.
Delays above 30 seconds return immediately without retrying early. A persisted
reference cooldown is at least 60 seconds or the provider delay if longer. Long
cooldowns do not block an application thread sleeping. Invalid/nonfinite headers
fall back to finite backoff.

Measured mock request counts: five timeframe loads use one discovery request;
six concurrent requests across two provider instances use one discovery request;
service calls with refresh `[false,false,true,false]` use two discoveries and two
OHLCV requests. A new provider instance reuses the on-disk cache. A first no-cache
429 is not hammered by subsequent requests during cooldown. A 120-second
Retry-After causes one HTTP request/no sleep; a 1-second header permits three
requests/two sleeps. Single flight is process-wide, not a distributed lease:
multiple worker processes can each start a fetch. No multiprocess guarantee.

## Portfolio facts and limitations

Current holdings show provider name, presentation ticker, quantity, average cost
per share, current price, reported wallet open cost/value/unrealised P&L, and
unrealised return = reported wallet P&L / reported wallet cost × 100 (positive
cost required). Price currencies and wallet currencies remain separate. Short
tickers are display abbreviations; full provider identities remain in details.

Account cards expose reported totalValue, investments.currentValue/totalCost/
unrealizedProfitLoss/realizedProfitLoss and cash.availableToTrade. Unrealised
return uses the same cost formula. Missing fields are unavailable, never zero or
inferred by multiplying quantity with a price from another currency.

Dividends are available as individual history records, but no authoritative
account dividend total is returned in the summary. No total-return/cash-flow
model was added. Both summary cards explicitly say unavailable. No equity curve,
tax lots, currency summation or FX inference was introduced. Previous position
snapshots stay accessible and are marked no longer held. Provider IDs/raw facts
are in expandable details; timestamps are human-readable in the displayed zone.
An empty manual ledger no longer emits unrelated USD-zero summary cards.

Sources: [official positions](https://docs.trading212.com/api/positions) (share
prices in instrument currency; wallet facts separately),
[official account summary](https://docs.trading212.com/api/accounts/getaccountsummary).
Existing normalization already preserved these fields, so no new broker API
calls or broker mapper changes were needed.

## Verification

Final full backend, isolated temporary database/cache paths:

```powershell
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp "$env:TEMP/ledger-cp8-final-<unique>"
```

**428 passed**, zero failures, 52.21s. Two existing dependency deprecations remain
(Starlette/httpx, AnyIO BlockingPortal). The new tests account for 20 cases:
18 reference-cache/rate-limit cases and two broker-extension cases.

Focused: **347 passed**, zero failures, 47.81s, same two warnings:

```powershell
.venv/Scripts/python.exe -m pytest -q tests/test_massive_reference_cache.py tests/test_broker_extension_contract.py tests/test_release_replay.py tests/test_release_journal.py tests/test_phase6_journal_report.py tests/test_phase63_journal_research.py tests/test_phase5_engine.py tests/test_phase56_replay_workspace.py tests/test_phase561_replay_consistency.py tests/test_phase55_research_and_replay.py tests/test_phase4_journal.py tests/test_oanda_journal_import.py tests/test_momentum_vcp_baseline.py tests/test_journal_v2.py tests/test_journal_diagnostics.py tests/test_intraday_baselines.py tests/test_gold_experiments.py tests/test_futures_foundation.py tests/test_broker_sync.py tests/test_broker_connections.py tests/test_strategy_workspace.py -p no:cacheprovider --basetemp "$env:TEMP/ledger-cp8-focused-final-<unique>"
```

The focused run covers Gold variants/frozen reference, Momentum, ORB/VWAP,
existing continuous charts/dated economics, Replay causality, OANDA, Trading 212,
profiles, Workspace and Journal preservation. The standalone cache suite also
passed all **18 cases** in 2.26s. `git diff --check` passed. Owned browser/server
helpers were stopped; no listener remained on their isolated ports.

Frontend: `node --test tests/*.test.js`: **20 passed**, zero failures, 178.52ms.
`npm.cmd run build -- --outDir "$env:TEMP/ledger-cp8-build-final"`: **passed**,
71 modules, 1.52s. Existing >500kB bundle warning remains. No dependency additions.

Isolated headless Chrome, final production build, synthetic HTTP MockTransport
fixtures, separate temporary data/strategies, external requests blocked:

- Trading 212 friendly position identity, independent USD share prices/GBP wallet
  amounts, cost/value/P&L/return cards and unavailable dividend/return totals.
- Empty manual summaries hidden; provider IDs only visible in details.
- Notes saved and preserved across duplicate sync; provider cost remains intact.
- OANDA Journal sync/table rendering and no page overflow at 1024 × 900.
- No observed runtime exceptions. No real provider/account acceptance claimed.
- Evidence: `%TEMP%/ledger-cp8-smoke-xc_wag4_/holdings-1024.png` and smoke helpers.
  The initial Journal selector expected “Columns” instead of “Visible columns”;
  correcting that smoke selector resolved the timeout, without application edits.
- The initial independent adapter fixture omitted required fees; fixed the
  fixture, then reran tests. No Journal production change was necessary.

## Frozen rules and remaining work

Gold baseline/variant formulas are unchanged; exact formulas remain in
GOLD_EXPERIMENTS.md. Momentum/VCP, ORB/VWAP, engine execution, Replay reveal timing
and drawings are unchanged. Existing regressions were run, not rewritten.

**Outstanding:** generic versioned roll schedule; additional per-bar provenance;
TradingView-style adjustment where verifiable; raw dated fills behind NQ1! in
Backtest/Replay; open-position/pending-order roll handling; dual alias/dated
Journal identities; real NQ roll-period comparisons; NQ1! browser acceptance.
Current NQ1! selection remains calendar-front-v1 and chart-only. Back-adjustment
still uses backward-additive-observed-gap-v1. Neither is TradingView parity.

No NQ1! Replay/Backtest, roll-marker or Gold comparison browser check is claimed
as newly performed in this save point. Those are required for final checkpoint 8
acceptance after implementation. No checkpoint 9 work was started.

## Manual acceptance for this save point

1. With an authorized Massive setup, switch NQ1! 1m/5m/15m/1h charts and inspect
   request counts: fresh references should not be rediscovered on each switch.
   Restart Ledger and confirm durable reuse. Manual refresh may update metadata.
2. Use an isolated mock for 429 checks; verify stale-reference reuse and a clear
   missing-cache error. Do not intentionally rate-limit a live provider.
3. Sync Trading 212 read-only. Compare positions and account totals with the
   official broker snapshot; verify each displayed currency, cost and P&L.
4. Open provider details, inspect full ticker/raw dates, edit notes, sync again;
   confirm notes and facts survive. Inspect dividend history separately.
5. Confirm manual transactions still show their own holdings/history and that
   an empty manual ledger does not add unrelated zero summary cards.
6. At 1024px, inspect holdings, details, notes and Journal. Defer continuous-alias
   trading acceptance until the remaining execution work has been implemented.
