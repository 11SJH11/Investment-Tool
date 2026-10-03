# Broker import extension contract

The current user/configuration contract is [Broker connections](BROKER_CONNECTIONS.md).

## Two destinations, one execution representation

`app/brokers/executions.py` defines validated canonical `Execution` evidence:
provider, environment, opaque account key, execution/order/position IDs, symbol,
asset class, side, provider quantity unit, price, UTC timestamp, signed cost/P&L
facts and allowlisted audit metadata. Missing monetary facts stay null. A
TradeLocker order aggregate is explicitly distinguished from a deal fill.

TradeLocker and MT5 normalize before shared `services/execution_sync.py` reconstructs
fully closed positions. Trading 212 normalizes fills into the same store but keeps
its Portfolio snapshot/review destination; a holding is not a closed Journal trade.
Its unavailable position ID stays empty and cannot enter position reconstruction.
OANDA retains its mature existing `BrokerHistoryAdapter`/`HistoryBatch` mapping and
unchanged identities; it is not forcibly remapped through a new allocation model.

## Persistence

Schema 17 adds `broker_executions`, keyed by provider/account/external execution ID,
with position ID and canonical JSON. No secret/account-login data is stored there.
Executions, Journal facts and cursor share one transaction; Portfolio facts and
canonical fills also share their existing atomic transaction. Failure leaves last
good facts/cursor intact. Review fields, attachments and imported row IDs remain
repository-owned. Corrections that invalidate a closed trade fail for reconciliation.

Legacy Journal SQLite requires a non-null `fees` value. For canonical unknown costs,
only that legacy storage slot uses zero; canonical evidence remains null and every
Journal repository decode returns `fees=null` with `costs_complete=false`. Neither
net P&L nor R is computed from that storage placeholder. No risky table rebuild was
needed to change nullability. Existing manual/OANDA behavior is unchanged.

## Adapter registration

Register factories/capabilities in `broker_connections.py`, configuration in
`profiles.py`/`config.py`, and safe UI capabilities. New history adapters expose
`accounts()`, `connect(selected_key)`, `read_executions(cursor)`, and `close()`.
The old OANDA protocol remains intact. Accounts are verified before sync; selected
keys and enable/environment preferences are local non-secret settings. HTTP client
and native module injection allow deterministic tests without live credentials.

New adapters must validate full response shape, finite quantities/prices, identities,
timezones, completeness and pagination boundaries. Unknown instruments must never
be guessed. Declare any aggregate/timestamp/retention limitation. Never add live
order calls, provider-controlled URLs, raw exception bodies or secret logging.

Tests must cover partials, duplicate sync, account/environment separation, incremental
reconciliation, failure rollback, review/media preservation, unknown symbols,
missing costs, and repeated initialization. A future MT4 or CSV transport can reuse
this boundary, but neither transport is implemented by the MT5 connector.
