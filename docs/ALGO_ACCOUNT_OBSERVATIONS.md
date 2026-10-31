# Recorded MT5 account monitoring

Algo Trading now displays actual **persisted observations** obtained through the
existing read-only MT5 snapshot adapter. It does not enable a strategy worker or
infer trade attribution from an account, symbol, timestamp or magic number alone.

Select the verified account in Settings, then use **Refresh broker observation**
in Algo Trading. This explicitly calls the existing POST snapshot endpoint. Normal
page polling and **View recorded details** only read SQLite and never contact MT5.
Snapshots taken from Settings are persisted too. Account identity/environment are
checked before displaying results, including when account selection changes during
a request. Failed reads keep the previous facts with a stale-data warning.

The panel shows balance, equity, margin/free margin, position/order counts, observed
positions in a paginated shared table, and an interactive equity observation chart.
The chart uses UTC receipt times, not unverified broker tick timestamps. It is not
a strategy return curve: deposits, withdrawals, external trades and missing periods
are not removed. History is lazy-loaded, at most 1,000 points. Values remain in the
account's currency. Summary totals deduplicate account identity and separate both
environment and currency. No simulated balance is pooled with a broker balance.

## Persistence

Two additive tables are created on the first explicit snapshot/failure write:
`mt5_account_observations` (last verified facts and latest attempt status) and
`mt5_account_equity_observations` (scalar account history). Read endpoints do not
create tables. History is capped at 1,000 rows/account and 10,000 globally; the most
recent full snapshot is separate. Existing Journal records, reviews, import cursors,
strategy configuration and execution tables are not rewritten. There is no backfill
of invented observations and no need to reset/recreate a database.

## Verification

Full backend: **2,083 passed, 41 skipped** (565.77s). Frontend: **145 passed**.
Production build passed (181 modules). Focused monitoring/diagnostics tests passed;
new privacy, rotation, failure-stop, persistence, retention, identity-race and
currency/deduplication tests are included in the full suite. Existing deprecation
and bundle-size warnings remain. Mocked account browser acceptance verifies
390/1024/1440/1920 layouts, paginated positions, explicit refresh and retained facts
after failure. Genuine Fedora account acceptance remains an operator check.

## Limits

No automatic account sampling scheduler, trade attribution, realised strategy P&L,
cashflow-adjusted return, verified exposure calculation, start/resume/order controls,
or complete automated strategy deployment is claimed here. Those require the
separate DEMO execution system. This operator-facing read API reuses Ledger's
existing access boundary; it does not introduce multi-user ownership/authentication.
