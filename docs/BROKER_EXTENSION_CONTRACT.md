# Broker import extension contract

2026-09-18. No new broker networking or execution methods were added.

## Current boundaries

`app/brokers/base.py` defines BrokerHistoryAdapter with provider, account_key,
environment, account_label, capability_report(), accounts(), fetch_closed(cursor)
and close(). HistoryBatch contains normalized Journal facts and a next cursor.
Normalization is adapter-internal (OANDA uses `_map`), not a mandatory public
normalize_trade method. Transactions are fetched internally where necessary;
there is no generic transactions() interface today.

BrokerSyncRepository atomically applies a batch and its cursor. JournalService
protects execution facts for every `broker_` source, independent of provider.
Resync preserves review fields, attachments and row IDs. Original imported
metadata remains available after refreshed facts. A stale expected cursor cannot
overwrite a newer sync. Credentials must not enter normalized facts or metadata.

The new synthetic ExampleHistory test uses no OANDA mapping or networking. It
proves that a new provider can use existing Journal tables and review protection,
including account/environment-scoped identity, partial-fill metadata, stable IDs,
idempotency, attachments, repeat initialization and cursor conflict rejection.

## Honest limitation: registration is not yet fully generic

BrokerConnections dispatches Journal sync via an OANDA-specific branch and
BrokerSyncService reads OANDA-specific settings/constructor arguments. Provider
names, credential requirements and environments are allowlisted in profiles.py;
capabilities/factories are registered in broker_connections.py. Adding only a
factory entry is **not** enough to make another Journal broker operational.

A future adapter needs a small profile/dispatcher registration change (or a
bounded generic history dispatcher) alongside the adapter. It should not need
Journal database or review-UI rewrites. This audit does not broaden dispatch now,
claim existing support for another broker, or disguise a registration limitation.

## Canonical mapping obligations

| Meaning | Current normalized destination |
| --- | --- |
| Provider | source=`broker_<provider>`, external_provider |
| Account/environment | opaque external_account_key; account label; metadata environment |
| Identity | external_id scoped to provider/environment/account/trade; external_order_id |
| Instrument/side | ticker, direction |
| Filled size/prices | quantity, entry_price, exit_price; weighted fills if fully evidenced |
| Timestamps | opened_at, closed_at in UTC |
| Currency | account_currency and position_currency explicitly |
| Broker realized P&L | broker_realized_pnl; costs and net pnl_amount separately |
| Costs | fees, commission, financing, applicable other cost fields, costs_complete |
| Fills/order IDs | source_metadata entry/exit fill arrays and external order IDs |
| Review | Never owned by the adapter; common JournalService review path |

Use explicit unavailable values when initial risk, conversion or cost allocation
cannot be established. Do not reconstruct complete executions from an arbitrary
page of order history. A partial close must update the same trade identity when
fully closed; a netted-position API needs documented allocation semantics.
The adapter validates canonical numeric fields and required schema values before
returning a batch. The repository is a trusted internal boundary, not a validator
for arbitrary untrusted adapter code.

## Adding a future broker

1. Confirm official API entitlement, authentication, closed-trade/fill semantics,
   account scope and permitted read endpoints. TradeLocker, Tradovate and IBKR
   require their own evidence and adapter implementation; none is enabled here.
2. Implement an isolated GET/read-only history adapter with bounded pagination,
   retries, sanitized failures, deterministic normalization and an opaque cursor.
   Account identity must survive key rotation without exposing account secrets.
3. Register credential/environment validation, capability/status information,
   adapter construction and the Journal sync dispatch path. Unconfigured status
   must make zero history requests. Preserve existing OANDA profiles and identity.
4. Reuse BrokerSyncRepository and JournalService. Test account/environment
   collisions, partial fills, repeated imports, review/attachment preservation,
   atomic failure, cursor conflicts, secret handling and zero order methods.
5. Run all existing OANDA, profile, Journal and migration regressions.

Trading 212 remains a separate Portfolio snapshot adapter because holdings and
investment history are not evidence of closed trading positions. Tradovate's
existing scaffold remains unsupported. A future CSV adapter could normalize
verified rows into HistoryBatch with explicit file/row identities and currencies;
no CSV import feature is implemented in this checkpoint.

## Stage 12 official TradeLocker review (3 October 2026)

Implementation remains pending. These findings constrain the next stage; no
connection, authentication or history request has been made to a live account.

The public API separates demo/live hosts, uses JWT authentication and requires
`accNum` on trade routes. Account ID and accNum are different concepts. Runtime
configuration supplies column definitions and provider limits; do not freeze array
column offsets or invent a history row cap. See [Getting started](https://public-api.tradelocker.com/docs/getting-started)
and [configuration](https://public-api.tradelocker.com/reference/getconfigusingget).

Documented history is `GET /trade/accounts/{accountId}/ordersHistory` with UTC
millisecond `from`/`to` bounds; it includes final statuses other than filled.
Account discovery uses `GET /auth/jwt/all-accounts`. See [history contract](https://public-api.tradelocker.com/reference/getordershistory)
and [account discovery](https://public-api.tradelocker.com/reference/getallaccounts).

The [official Python client](https://github.com/TradeLocker/tradelocker-python/blob/main/src/tradelocker/tradelocker_api.py)
describes executions as current-session data and decodes them using filledOrdersConfig.
That is insufficient evidence to treat executions as a complete historical ledger.
Its [types](https://github.com/TradeLocker/tradelocker-python/blob/main/src/tradelocker/types.py)
separate order ID, position ID and execution ID; the execution columns shown there
do not establish complete historical fee/realised-P&L attribution.

Implementation decisions still required before enabling import:

- Preserve environment/account identity, distinguish orders from actual executions,
  and normalize through the shared execution boundary required by Stage 14.
- Decode config-labelled rows; traverse bounded time windows and detect saturation.
  If a minimum window cannot be proven complete, fail without advancing the cursor.
- Reconstruct positions only from supported opening/closing facts. Preserve partial
  order/position IDs; missing costs/P&L remain unavailable, not zero or guessed.
- Expose authentication POST only for token acquisition/refresh; broker-data access
  is GET-only. No order mutation methods. Keep tokens/passwords memory-only.
- Preserve existing OANDA identities and Portfolio behaviour. The present dispatcher
  is OANDA-specific for Journal, so factory registration alone is not sufficient.

The public documentation and official client are the sources, not third-party
copy-trading wrappers. Broker/account-dependent config and historical availability
still need fixture contracts and optional live acceptance before claiming support.
