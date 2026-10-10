# MT5 market data, Robinhood Portfolio and automation provenance

Status: implemented with deterministic fixtures; live terminal/broker acceptance is still required. No orders can be placed by this integration. Existing OANDA XAUUSD and the default Massive futures route are preserved.

## MT5 setup

1. Install the official MetaTrader 5 terminal on the Windows machine running the backend. Obtain an account with genuine CME NQ/MNQ and expired-contract history. A Nasdaq CFD account is insufficient.
2. In the backend virtual environment run `python -m pip install MetaTrader5`. The package is optional, not imported on normal startup. Official package 5.0.6231 constants were inspected for this implementation, without installing or connecting it during verification.
3. Configure `MT5_LOGIN`, `MT5_SERVER`, optional `MT5_PASSWORD` and `MT5_TERMINAL_PATH`, and `MT5_ENVIRONMENT=demo` or `live`. Use an account whose tick values are expressed in USD; account-currency-converted tick values fail strict economics validation.
4. Log the terminal into that exact account/server. Enable the required symbols and load history. Increase terminal **Max bars in chart** if needed. Ledger cannot manufacture history the broker does not provide.
5. Set `MT5_MARKET_DATA_ENABLED=true` and `MT5_FUTURES_MAPPINGS_JSON` in backend configuration. Keep `FUTURES_DATA_PROVIDER=massive` initially. Market data and the existing `MT5_ENABLED` Journal import are independent.

Example mapping (names only, no credentials):

```json
{"NQ":{"template":"{root}{month}{yy}","contracts":{"NQZ26":"your-broker-NQZ26"}},"MNQ":{"template":"{root}{month}{yy}"}}
```

Explicit dated mappings take priority; template placeholders are root, month, yy and year. A broker symbol named NQ can be mapped to a particular dated contract only when its actual expiry matches that contract. Never reuse a rolling alias as historical evidence for multiple expiries.

Validation requires futures calculation mode, CME description/path/exchange evidence, USD profit currency, listing/expiry dates, and correct economics: NQ tick 0.25, tick value $5, point value $20; MNQ tick 0.25, tick value $0.50, point value $2. Expiry month/year must match. NAS100/US100/USTEC/CFD identifiers fail validation and are explicitly distinct instrument metadata. XAUUSD stays OANDA spot/CFD gold; GC/MGC are separate futures aliases.

Only completed OHLC bars are returned, in UTC, in [start,end). Identical duplicates are removed; conflicting duplicates, malformed values and empty ranges fail. Exchange `real_volume` is retained, including reported zero: tick volume is never substituted. Daily/weekly completeness uses a conservative fixed-duration check, not a new exchange calendar. Tick history is not implemented in this phase.

## Contracts and cache

NQ/MNQ quarterly candidates use H/M/U/Z and verified terminal listing/expiry metadata. Missing expired symbols fail rather than generating metadata. Continuous MT5 uses the shared existing **calendar-front-v1** stitcher: retain the nearest dated contract through its last-trade UTC date, then switch at 00:00 UTC the following day. Raw prices, source contract, roll method/version, effective date and expiry remain attached. This differs from Massive's default prior-session-volume45-v1 and is not asserted to match TradingView. Engine/Replay economics and roll-position handling are unchanged.

Existing Parquet MarketStore and SQLite coverage tracking are reused by Charts, Replay and backtests. MT5 namespaces include a hash of account/server/environment/mapping; secrets are not cache paths. Repeat requests use cache, missing head/tail ranges are fetched, continuous data references underlying raw-contract manifests. Refresh uses existing invalidation. Coverage denotes requested ranges, not guaranteed continuous market sessions: gaps may include closed sessions, sparse trading or terminal truncation. Check observed first/latest bars before research. Cached data can outlive terminal connectivity, and a cache hit does not prove the terminal is currently connected.

## Comparison and diagnostics

Settings > Futures provider diagnostics: choose NQ1!, MNQ1! or a dated contract, timeframe and UTC dates (exclusive end, at most 31 days). **Test MT5 history** probes one feed; **Compare Massive / MT5** probes both through cache and repeats a warm request. Expand details for OHLC/volume absolute differences, nonmatching timestamps, gaps, duplicate counts after normalization and contract/roll provenance. Identical normalized timestamps are compared; separate dated-contract comparisons avoid attributing roll differences to feed errors.

API: `POST /api/data/futures/diagnostics` with `{symbol,timeframe,start,end,compare}`. Example times: `2026-09-01T00:00:00Z` to `2026-09-02T00:00:00Z`. No default changes. Durations include normalization/storage, not just network download. Gaps include weekends/closures; reported depth is observed within the requested window, not the provider's entire entitlement. Normalized duplicate counts do not capture duplicates already removed by an upstream adapter.

Only after actual comparison, explicitly set `FUTURES_DATA_PROVIDER=mt5` and restart normally to select MT5 for NQ/MNQ. Other futures and OANDA remain on their existing providers. No live comparison was performed for this handoff.

## Robinhood supported boundary

Robinhood officially documents a Trading MCP endpoint at `https://agent.robinhood.com/mcp/trading`, OAuth authorization and reads of normal accounts as well as agentic accounts. See [official onboarding](https://robinhood.com/us/en/support/articles/onboarding-an-external-agent/) and [official tool capabilities](https://robinhood.com/us/en/support/articles/trading-with-your-agent/). This is distinct from the crypto-only REST API. Normal holdings are **not** claimed to be unavailable.

Ledger implements an explicit read-tool allowlist: get_accounts, get_portfolio, get_equity_positions, get_option_positions, get_crypto_positions. Tools and input schemas are discovered before calls. Account-scoped identifiers are required; unsupported schemas, pagination or conflicting returned account identity fail without replacing the prior snapshot. Cursor pagination is bounded. Structured response normalization is fixture-tested, but **authenticated live output schemas and entitlement have not been verified**. A real response may require a narrow adapter update; do not treat this as live-certified support.

1. Obtain authorized OAuth access to the official Trading MCP using Robinhood's documented external-agent process and supported account permissions.
2. Set `ROBINHOOD_ENABLED=true`, `ROBINHOOD_PORTFOLIO_SYNC=true`, and backend-only `ROBINHOOD_ACCESS_TOKEN`. Optional `ROBINHOOD_ACCOUNT_ID` selects a verified discovered identity. Do not put tokens in VITE variables or browser storage.
3. Restart normally, open Settings > Broker connections, Test connection, select a verified account, then Sync now. Multiple normal/agentic accounts retain separate opaque provider-qualified identities; account labels never imply automated origin.
4. Inspect holdings, costs, reported values and account summary in Portfolio. Repeated sync updates stable records and retains notes/tags. Failure or loss of previously granted asset read capability preserves the last snapshot. Broker scheduler uses a 300-second minimum and existing Retry-After backoff.

There is no built-in OAuth browser callback, refresh-token management or password login. Expired tokens require renewed official authorization and backend token replacement. Availability/access may depend on Robinhood account eligibility. Transaction-history tools are documented by Robinhood but not imported by this initial holdings adapter. Unknown fields/values stay unavailable; cash is not inferred from buying power. Only provider-reported values are used.

Portfolio broker filtering keeps per-account holdings distinct. Account totals group by currency, deduplicate provider/account identity and sum each reported account total once, without adding holdings or cash again. Incomplete totals remain unavailable. Different sync timestamps are shown; this is not a synchronized multi-account valuation or FX conversion.

## Execution and automation

ExecutionProvider is a small capability boundary with a read-only destination. All Ledger execution capabilities are false and submit always rejects. Discovered Robinhood order-tool availability is reported separately from Ledger permission. Robinhood documents equity/options/crypto agent tools; this implementation does not call them and does not infer futures/fractional/order-type support. A live risk gateway, account permissions and tested sizing are prerequisites to any later execution adapter; the historical BacktestEngine is not a live risk engine.

Migration 18 adds nullable is_automated, execution_source, strategy_id, strategy_name and strategy_run_id to Journal. Existing manual/Replay rows become Manual; backtest rows become Automated/strategy; broker imports remain Unknown/imported unless explicit evidence exists. MT5 Expert Advisor/script entry reasons establish Automated/imported, while magic numbers, account labels and automated stop/target exits alone do not. Mixed positions with any evidenced programmatic entry are marked Automated; individual deal reasons remain in audit metadata. No external strategy name is invented.

Journal cards/table display a subtle Automated label. Structured filters include Manual/Automated/Unknown, execution source and strategy name. The same dimensions are available to analytics. Normal broker review cannot modify execution/provenance facts. Initialization is additive and repeat-safe, preserving IDs, reviews and attachments.

## Verification and remaining acceptance

Run `./Verify-Ledger.ps1` from the repository; it uses isolated data and build artifacts. All provider tests are mocked; no user's dotenv values are read. The focused suites are test_mt5_market_data.py, test_futures_diagnostics.py, test_robinhood_portfolio.py, test_journal_automation.py and existing MT5/canonical broker suites. See the handoff for exact final results.

Manual acceptance still required: real MT5 dated and continuous history for 1m/5m/15m/1h; cache repeat and missing-range checks; NQ/MNQ contract economics across a roll in Chart/Backtest/Replay; official Robinhood OAuth/live schema/account discovery and repeated sync; account separation, notes preservation and missing permission behavior. Neither provider has been switched globally or live-tested during implementation.

Official MT5 references: [symbol metadata](https://www.mql5.com/en/docs/python_metatrader5/mt5symbolinfo_py), [UTC/history limits](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesrange_py), [deal reasons](https://www.mql5.com/en/docs/constants/tradingconstants/dealproperties).

## Exact change manifest

This integration only; pre-existing strategy/research files are excluded and preserved.

New files:

- `backend/app/brokers/execution_provider.py`
- `backend/app/brokers/robinhood.py`
- `backend/app/core/automation.py`
- `backend/app/data/calendar_front.py`
- `backend/app/data/providers/metatrader5.py`
- `backend/app/services/futures_diagnostics.py`
- `backend/tests/test_futures_diagnostics.py`
- `backend/tests/test_journal_automation.py`
- `backend/tests/test_mt5_market_data.py`
- `backend/tests/test_robinhood_portfolio.py`
- `docs/MT5_ROBINHOOD_INTEGRATION.md`
- `frontend/src/features/settings/FuturesDiagnosticsPanel.jsx`
- `frontend/tests/browser/broker-integrations.mjs`

Modified files:

- `.env.example`
- `backend/app/api/data.py`
- `backend/app/brokers/executions.py`
- `backend/app/brokers/metatrader5.py`
- `backend/app/brokers/profiles.py`
- `backend/app/core/config.py`
- `backend/app/core/journal_analytics.py`
- `backend/app/data/futures.py`
- `backend/app/data/instruments.py`
- `backend/app/data/providers/massive_futures.py`
- `backend/app/services/broker_connections.py`
- `backend/app/services/broker_scheduler.py`
- `backend/app/services/container.py`
- `backend/app/services/journal.py`
- `backend/app/services/market_data.py`
- `backend/app/storage/broker_sync_repository.py`
- `backend/app/storage/database.py`
- `backend/app/storage/journal_repository.py`
- `backend/app/storage/portfolio_broker_repository.py`
- `backend/tests/conftest.py`
- `backend/tests/test_data_api.py`
- `backend/tests/test_journal_v2.py`
- `backend/tests/test_mt5_import.py`
- `docs/README.md`
- `frontend/src/api/client.js`
- `frontend/src/features/brokers/BrokerProfilesPanel.jsx`
- `frontend/src/features/brokers/brokerConnectionUtils.js`
- `frontend/src/features/journal/JournalFilters.jsx`
- `frontend/src/features/journal/TradesView.jsx`
- `frontend/src/features/journal/journalTable.js`
- `frontend/src/features/portfolio/BrokerPortfolioPanel.jsx`
- `frontend/src/features/portfolio/brokerPortfolioUtils.js`
- `frontend/src/features/settings/SettingsPage.jsx`
- `frontend/tests/brokerConnections.test.js`
- `frontend/tests/brokerPortfolio.test.js`

## Final automated results (2026-10-07)

- Full backend: `python -B -m pytest tests -q -p no:cacheprovider` through Verify-Ledger.ps1: **833 passed**, one existing Starlette/httpx deprecation warning. Includes broker reconciliation, migrations/media preservation, engine, Replay, Gold and research regressions.
- Full frontend: `node --test tests/*.test.js`: **124 passed**, zero failures.
- Focused final import regression: test_mt5_import.py, test_robinhood_portfolio.py, test_canonical_broker_acceptance.py: **36 passed**.
- Earlier focused diagnostics/migration/API run: **19 passed**; earlier new MT5/Robinhood/automation run: **26 passed**. These overlap the full suite and are not additive totals.
- Production build: passed. Direct `node verify-build.mjs C:/Users/jamie/Project/integration-final-direct-oct7` returned exit 0. The combined PowerShell redirected log reports a wrapper NativeCommandError for Vite's large-chunk warning after the build succeeds; its final line confirms verification passed. The direct build independently confirms success.
- Isolated browser: broker-integrations.mjs with mocked APIs, Robinhood/live-only selection/test/sync, no initial mutating call, MT5 diagnostic action, broker filtering/account totals at 1024/1440/1920. No runtime errors or page overflow.
- Integration diff whitespace check: clean. Whole-index check still reports pre-existing trailing whitespace in `backend/app/backtesting/strategies/turtle_donchian_research_v1.py:134`; that user-staged strategy was not edited.
- No live broker/MT5 requests, credential reads, user database migrations, provider switches or orders were performed. Changes remain in the current tree; unrelated staged work was not committed.

Verification log: `C:/Users/jamie/Project/integration-final-oct7.log`. Final gate artifacts: `C:/Users/jamie/Project/integration-final-oct7/`.
