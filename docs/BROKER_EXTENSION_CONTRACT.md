# Checkpoint 8C: Journal broker extension audit

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
