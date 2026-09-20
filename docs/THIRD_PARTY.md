# Third-party software and inspiration

No dependency was added in Checkpoint 12. No upstream application source was
copied or vendored from OpenCharts, OpenTerminal, LedgerView or LuxAlgo.
OpenCharts was inspected for separation of drawing concerns; the implementation
here uses Ledger's existing timestamp/price model and Lightweight Charts APIs.

Runtime packages remain React/React DOM (MIT) and TradingView Lightweight Charts
(Apache-2.0, with bundled tslib portions under BSD-0-Clause). Build dependencies
and backend packages retain their own installed LICENSE/copyright notices; keep
these when distributing dependencies. Exact frontend versions are in package-lock.json.

Lightweight Charts is created by TradingView, Inc. Preserve its Apache license
and upstream notices in distributions. Its default chart attribution logo/link
is retained. TradingView: https://www.tradingview.com/ . The installed npm package
README also requires a user-visible creator attribution; Settings includes it.
No provider's market-data redistribution rights are granted by library licenses.

Workspace runs trusted user Python. Provider credentials and user databases are
not distributable build assets. Autochartist remains network-disabled scaffolding;
no portal scraping or third-party article republishing is implemented.
