# Read-only broker connections

Trading 212 feeds Investment Portfolio. OANDA, TradeLocker and MetaTrader 5 feed the common Journal.
Tradovate is readiness scaffolding only: even complete credentials never cause a
remote request. None of these adapters exposes execution or broker mutation methods.

## Configuration

Configure the backend `.env`, using the [safe root template](../.env.example) for the names. Never commit a
populated `.env`. Credentials are not entered, stored or returned by the frontend.

- OANDA retains `OANDA_ACCESS_TOKEN`, `OANDA_ACCOUNT_ID`, `OANDA_ENVIRONMENT`.
  Its existing default account, import IDs, cursor, partial-close mapping and review
  protection are unchanged. Market-data routing remains unchanged.
- Trading 212 uses `TRADING212_ENABLED`, `TRADING212_API_KEY`,
  `TRADING212_API_SECRET`, `TRADING212_ENVIRONMENT=demo|live`.
- Tradovate placeholders are `TRADOVATE_ENABLED`, `TRADOVATE_CLIENT_ID`,
  `TRADOVATE_CLIENT_SECRET`, `TRADOVATE_ACCOUNT_ID`,
  `TRADOVATE_ENVIRONMENT=demo|live`. Status is Not configured or Unsupported.

For additional accounts, `BROKER_PROFILES_JSON` is a JSON array. Example shape
(replace placeholders locally; do not put real credentials in repository files):

```dotenv
BROKER_PROFILES_JSON='[{"id":"oanda-live","provider":"oanda","environment":"live","enabled":true,"credentials":{"token":"LOCAL_TOKEN","account_id":"LOCAL_ACCOUNT"}},{"id":"invest-second","provider":"trading212","environment":"demo","enabled":true,"credentials":{"api_key":"LOCAL_KEY","api_secret":"LOCAL_SECRET"}}]'
```

Profile IDs must start with a lowercase letter and contain lowercase letters,
digits or hyphens, up to 60 characters. Do not use an account number or secret as
the profile ID. Reserved default IDs are `oanda-default`, `trading212-default`,
`tradovate-default`, `tradelocker-default`, `mt5-default`. Extra Tradovate profiles use `client_id`, `client_secret`,
`account_id`. Restart the backend after changing configuration. Invalid JSON,
duplicate IDs and invalid extra-profile environments fail with a sanitized error.

Status/Settings requests make no remote probes. Incomplete credentials disable
sync and cause zero history calls. "Configured" means local configuration is
present, not that credentials have been remotely validated. Each profile has an
explicit Sync button. OANDA default also retains the old Journal sync endpoints.

## Architecture and identities

`BrokerHistoryAdapter` defines safe capabilities/accounts and `fetch_closed(cursor)`
returning `HistoryBatch` normalized Journal facts. Existing `BrokerHistory` imports
remain compatible. Normalized OANDA facts already include provider/account/environment,
instrument, direction, units, entry/exit fills, timestamps, P&L/currency, costs,
external IDs and metadata. Cursor persistence and user review belong to the
repository, not the adapter. The provider registry/dispatch lives in
`services/broker_connections.py`; status paths do not construct unsupported adapters.

Trading 212 deliberately has a Portfolio snapshot contract rather than pretending
investment order history consists of closed Journal trades. Broker facts and local
notes/tags are separate. Account identity is SHA-256 of provider/environment/actual
provider account ID; credential rotation does not create a duplicate account.
OANDA uses its unchanged identity formula. Identical trade IDs across accounts or
environments cannot collide. Profile bindings retain only an opaque account key,
and are scoped to environment/API-key fingerprint to avoid stale account status
after configuration changes. No raw account number is returned or saved for T212.

## Official Trading 212 API contract

Verified against official documentation on 2026-09-16:

- [Authentication, pagination and limitations](https://docs.trading212.com/)
- [Account summary](https://docs.trading212.com/api/accounts/getaccountsummary)
- [Positions](https://docs.trading212.com/api/positions/getpositions)
- [Historical orders and fills](https://docs.trading212.com/api/historical-events/orders_1)
- [Dividends](https://docs.trading212.com/api/historical-events/dividends)
- [Cash transactions](https://docs.trading212.com/api/historical-events/transactions)

The adapter uses HTTP Basic key/secret authentication against fixed official demo
or live hosts. Its only request method is GET. Endpoints are account/summary,
positions, history/orders, history/dividends and history/transactions under
`/api/v0/equity/`. No report-generation POST or order endpoint is implemented.
Pagination accepts only relative nextPagePath values for the same history endpoint;
external hosts, redirects, endpoint switches and loops are rejected. History pages
use limit 50. Rate-limit headers are honored, 429 retries are bounded, and errors
never echo response bodies, request headers or transport exception messages.
Only selected documented fact fields are retained, not arbitrary provider bodies.

All history pages must complete before commit. Every explicit sync rescans history
so late postings and corrections are not skipped by an inferred timestamp cursor.
Order records use order ID plus fill ID (or an explicit order-only identity);
dividends/cash use provider reference. Duplicate identical records are harmless;
conflicting duplicate facts fail the sync. Account snapshot, position reconciliation,
history upserts, sync state and profile binding commit in one SQLite transaction,
with a stale-cursor check. A failed sync preserves the last successful data/cursor.
Old positions become inactive but retain IDs and notes; reappearing positions use
the same record. History never creates synthetic local BUY/SELL transactions.

## Storage and UI

Two additive tables: `portfolio_broker_accounts` (summary and sync timestamp) and
`portfolio_broker_records` (unique provider/account/kind/external ID, facts, active
flag, note, tags). Existing `broker_sync_state` and `app_settings` hold sync state
and bindings. Existing manual Portfolio, Journal, Playbook, Daily Review and media
tables are preserved. Repeated initialization is safe.

Settings shows all profiles and capabilities. Journal shows Journal destinations;
Investment Portfolio shows Trading 212 profiles, account summary, positions,
orders/fills, dividends and cash records. Broker accounts remain visibly separate
from the manual ledger totals. Each amount uses its reported currency. Instrument
prices and account-value currencies are distinct. Record facts are read-only;
only notes and tags have a mutation endpoint. API validation forbids fact fields
in review requests. Notes/tags survive sync and inactive holdings.

## Limitations

- The API is beta and is intended for Invest/Stocks ISA, not CFD/Cash ISA.
  Its account/position wallet values use the primary account currency; no complete
  multi-currency wallet reconstruction is claimed. Original instrument currencies
  and supplied cash transaction currencies are retained.
- Summary, positions and paginated history are separate remote reads, not a broker
  atomic snapshot. Ledger's local commit is atomic, but activity during sync can
  change provider facts. Sync again to refresh; no historical equity curve, tax-lot
  reconstruction or portfolio performance is inferred from incomplete history.
- A full scan has a 200-page per-history limit and a 180-second request/wait budget
  (a single in-flight request can add up to its 30-second timeout). Large or heavily
  rate-limited histories can fail safely and may require a future resumable import
  workflow. No partial scan is reported as a successful complete sync.
- Global Portfolio sync guard serializes T212 profiles in one process. OANDA
  profiles have independent guards; repositories reject stale concurrent commits.
- Removing a backend profile does not delete imported account data or reviews.
- Validation used synthetic HTTP transports, not real credentials/accounts.

## Current verification

See [broker acceptance](BROKER_IMPORT_ACCEPTANCE.md) for current test/build/browser
results. Automated imports use synthetic fixtures, never live credentials. Existing
OANDA/Portfolio identity and review-preservation regressions remain in the suite.

## Backend scheduling and activity

 backend lifecycle owns the schedule, with persisted app_settings preferences/cooldowns, OANDA minimum/default 60s and Trading 212 300s. Configured supported profiles are enabled by default; incomplete profiles make no calls. Manual Sync now remains. Same-profile active/pending work cannot overlap; OANDA additionally locks by account/environment. Provider 429s defer to the scheduler and honor Retry-After. Failures retain last successful data. Normal browser navigation has no effect on scheduling. The browser polls status only. Run one Ledger backend process: distributed/multi-worker scheduling is not implemented.

Activity: explicit provider BUY/SELL and supported Deposit/Withdrawal/Interest/Dividend/Fee directions are visible. Missing/ambiguous action or transfer direction stays Unavailable rather than being guessed from quantity sign.


## TradeLocker

Set `TRADELOCKER_ENABLED=true`, `TRADELOCKER_ENVIRONMENT=demo` (or `live`),
`TRADELOCKER_EMAIL`, `TRADELOCKER_PASSWORD`, `TRADELOCKER_SERVER` on the backend.
`TRADELOCKER_DEVELOPER_API_KEY` is optional if issued for your API access.
`TRADELOCKER_ACCOUNT_ID` is optional: prefer **Test connection**, then select a
verified account in Settings. The UI uses opaque account keys, never raw account
numbers. No credentials/tokens enter the database or browser preferences.

The adapter uses JWT token authentication and documented GET routes for accounts,
config, instruments, historical orders and open positions. Only authentication is
POST. Redirects and arbitrary routes are refused. See official
[authentication](https://public-api.tradelocker.com/docs/getting-started),
[history](https://public-api.tradelocker.com/reference/getordershistory), and
[configuration](https://public-api.tradelocker.com/reference/getconfigusingget).

Config supplies array column names, the history row cap and request pacing. A
saturated time window is split with inclusive overlap and stable-ID deduplication.
If a minimum window is saturated, data conflicts, an instrument is unknown, or the
512-request/180-second budget is exhausted, no facts/cursor are committed. A 429
returns a safe category and Retry-After to the backend scheduler.

Historical evidence is an **order aggregate**, using filled quantity/average price
and explicitly labelled order-last-modified timestamps. It is not an invented list
of individual deals. Current-session executions are not treated as full history.
Balanced position flows with matching instruments become closed Journal trades;
open/unbalanced flows remain canonical evidence. Ambiguous simultaneous opposing
orders and reversals fail reconciliation. Broker history retention can still limit
available evidence; no complete lifetime history or exact execution-time guarantee
is made. Unreported realized P&L, fees, commission and initial risk remain unavailable.

Incremental *reconciliation* applies changed stable IDs only, while the provider
history is reread in bounded windows to catch old orders finalized/corrected later.
The `from` parameter is not assumed to mean modification time. This is intentionally
not claimed to be an incremental network-history cursor.

## MetaTrader 5 (not MT4)

Install `backend/requirements-mt5.txt` in Ledger's backend Python environment only
when this connector is needed. It is optional for application startup and tests.
Run a logged-in **MetaTrader 5 terminal on the backend machine**, then set
`MT5_ENABLED=true` and `MT5_ENVIRONMENT=demo` or `live` to match the terminal.
`MT5_LOGIN`, `MT5_SERVER`, `MT5_PASSWORD`, and `MT5_TERMINAL_PATH` are optional:
blank values use the terminal's current login; login/server can pin the account.
The official integration may start the specified terminal during initialization.

Only initialize/account_info/history_deals_get/positions_get/symbol_info/shutdown
are called. No order methods exist in the adapter. One process-wide lock serializes
native-terminal access; account/server/environment are verified again after reading.
See official [Python integration](https://www.mql5.com/en/docs/python_metatrader5),
[deal history](https://www.mql5.com/en/docs/python_metatrader5/mt5historydealsget_py),
and [deal properties](https://www.mql5.com/en/docs/constants/tradingconstants/dealproperties).

A one-day overlap from the last successful timestamp discovers changed positions;
complete deal history is then retrieved by position ID. Tickets deduplicate fills.
Entries, exits, partial closes, scale-in/out, commissions, swaps and fees reconcile
before Journal creation. Cash-only account events are not fabricated into trades.
Position-linked separate cash adjustments and INOUT reversals fail safely instead
of inventing cost allocation or reversal lots. Closed-position corrections older
than the overlap require a deliberate future reimport workflow; automatic discovery
of arbitrarily backdated edits is not claimed.

Quantities retain **lots**. Current symbol contract size is recorded as current
metadata, not misrepresented as a historical conversion factor. Profit is taken
from provider deal facts, not recomputed with a guessed multiplier/FX rate.
Unallocated account charges are excluded from per-position deal P&L. Unknown
symbols, missing position openings or incomplete data block commit.

MT4 requires a separate adapter/transport; the MT5 package does not provide MT4.
It can later reuse canonical executions, account scoping and atomic reconciliation.

## Settings connection workflow

Trading 212, TradeLocker and MT5 cards offer connection tests, manual sync, last
successful sync, safe error category, persisted scheduling and environment controls.
TradeLocker/MT5 offer verified account selection. Environment changes do not reuse
another environment's selected account. Test connection reads account identity only;
it does not import history. Demo and live both remain read-only.

**Disconnect** disables that local profile persistently and preserves imports,
reviews, notes and attachments. It does **not** erase credentials from environment
configuration. Ledger has no secure credential vault, so this UI does not claim to
remove stored secrets; remove them from local configuration yourself when desired.
Enable connection restores eligibility. Normal restart is needed after changing
backend environment credentials; do not interrupt active research to restart.

New Journal providers use the existing minimum/default 60-second backend schedule.
Trading 212 remains 300 seconds. Rate-limit backoff can extend the next run. One
backend process per database remains required; locking is not distributed.
