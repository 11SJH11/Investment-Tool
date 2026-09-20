# Read-only broker connections — checkpoint 2

Trading 212 feeds Investment Portfolio. OANDA feeds the existing common Journal.
Tradovate is readiness scaffolding only: even complete credentials never cause a
remote request. None of these adapters exposes execution or broker mutation methods.

## Configuration

Configure the backend `.env`, using `.env.example` for the names. Never commit a
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
`tradovate-default`. Extra Tradovate profiles use `client_id`, `client_secret`,
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

## Checkpoint verification

- Full backend: **260 passed**, 2 pre-existing deprecation warnings, 27.70s.
  Includes 28 new broker-connection cases plus all prior OANDA, migration, engine,
  Gold, Momentum, Replay and Journal regressions.
- Initial existing OANDA/Journal compatibility check: **21 passed**.
- Frontend utilities: **7 passed**.
- Production build: **passed**, 65 modules, 7.51s; existing chunk-size warning.
- Isolated Chrome, synthetic broker data, blocked real outbound requests:
  Settings capability states/disabled buttons; explicit Portfolio sync; 5 imported
  records; repeat sync creates 0 and refreshes 5; saved position note preserved;
  two fills of one order displayed separately; 1024px page width without overflow;
  no observed runtime exceptions. Screenshots/helpers are in temporary directory
  `ledger-cp2-smoke-zunlqz63`, not production source.

Manual acceptance: configure a read-only demo profile, restart, sync explicitly,
inspect positions/history/currencies, save notes/tags and resync. Add another
profile and confirm independent account/environment identity. Verify OANDA reviews
and prior imported IDs survive. Tradovate must remain disabled/unsupported.

## Backend scheduling and activity

 backend lifecycle owns the schedule, with persisted app_settings preferences/cooldowns, OANDA minimum/default 60s and Trading 212 300s. Configured supported profiles are enabled by default; incomplete profiles make no calls. Manual Sync now remains. Same-profile active/pending work cannot overlap; OANDA additionally locks by account/environment. Provider 429s defer to the scheduler and honor Retry-After. Failures retain last successful data. Normal browser navigation has no effect on scheduling. The browser polls status only. Run one Ledger backend process: distributed/multi-worker scheduling is not implemented.

Activity: explicit provider BUY/SELL and supported Deposit/Withdrawal/Interest/Dividend/Fee directions are visible. Missing/ambiguous action or transfer direction stays Unavailable rather than being guessed from quantity sign.
