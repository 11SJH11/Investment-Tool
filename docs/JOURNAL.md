# Journal data, review and preservation

## Schema and preservation

Schema version 16 adds Journal Playbook links, setup grade, plan adherence, JSON review answers, account-scoped broker identity, account currency, broker realised P&L, financing, commission, guaranteed fees, dividends, initial risk and cost-completeness fields. Playbooks gain JSON sections and question definitions. A broker_sync_state table stores provider, hashed account/environment identity, cursor, last success and sanitized status/error. No tokens are stored.

Existing daily_reviews and media_attachments columns remain. Legacy freeform fields and attachment slots are retained. Existing source-constraint migration remains preserving: shared rows are copied and checked before its existing table replacement; unknown columns/custom indexes/triggers stop migration instead of discarding them. V2 additions are additive. Repeated initialization is tested. IDs, notes, timeframe notes, source metadata, external IDs, Playbook rules, daily reflections and all attachment ownership/slot records survive the pre-V2 fixture. Playbook deletion clears the link while retaining the trade's custom answers.

Keep the existing backend/data directory, database and uploads when updating. Normal startup applies the migration; no replacement database is supplied. Existing date-only daily reflections remain on their saved date/account when the Journal timezone changes.

## Broker implementation and guarantees

The small BrokerHistory protocol/HistoryBatch interface is separate from market-data routing. OANDA uses official account summary, closed trade pages and transaction history. Its transport exposes only GET. There are no broker order/position mutation methods or endpoints. Ledger's local POST sync action performs GET requests to OANDA.

One logical OANDA Trade ID maps to one common Journal row; identity includes provider, environment and hashed account. Partial closes reconcile units and realised P&L, and use their unit-weighted actual fill prices. The original opening fill, closing transaction IDs, underlying reduction fills, historical initial protection and cost metadata are retained. Sync commits all rows and the cursor atomically; failure retains previous rows/cursor. A local lock and database cursor comparison prevent competing syncs from overwriting each other. Resync excludes all discretionary fields and screenshots, and retains the original import metadata.

Incomplete credentials cause zero account-history calls and no adapter construction. Status does not fetch account history; the backend scheduler reconciles complete configured profiles. Errors omit request credentials, provider bodies and full account paths. Account labels use a hash prefix. Tests use generated/synthetic credentials only, never real tokens.

Accounting: broker realised P&L + financing + dividends - attributable commission - guaranteed execution fee. Spread is already in executions; halfSpreadCost is metadata only. Missing financing/commission or ambiguous multi-trade fees leave net P&L/result unavailable. Initial stops/targets come only from unambiguous ON_FILL historical protection, never current modified orders or price action. R requires initial stop risk and historical quote-to-home loss conversion when currencies differ; otherwise R is unavailable.

Official contracts checked: [Trade definitions](https://developer.oanda.com/rest-live-v20/trade-df/), [Trade pagination](https://developer.oanda.com/rest-live-v20/trade-ep/), [Transaction definitions](https://developer.oanda.com/rest-live-v20/transaction-df/), [Conversion primitives](https://developer.oanda.com/rest-live-v20/primitives-df/).


## Current user workflow

Trades uses the shared DataTable or persistent cards; search/header/+ Filter rules
are OR within fields and AND across fields. All matching rows feed statistics.
Calendar uses entry date in the chosen timezone; Daily Review is date/account scoped.
Currency totals stay separate. Analysis is descriptive, with N and low-sample labels.
Custom Playbook question IDs, renamed answers, old notes and every attachment slot
remain accessible. Broker facts cannot be edited through discretionary review.
Replay auto-journal defaults on; Settings can disable it, with an explicit Save
closed trade action. Deterministic identities still prevent repeated saves.

## Statement import preparation

`app.services.statement_import.preview_statement` is a tested, write-free boundary
for generic completed-trade CSV rows with explicit column mapping, timezone offsets,
stable account-scoped IDs and currencies. It does not reconstruct raw fills. Bad
rows return safe line errors; no arbitrary cell/account values appear in errors.
This release does not expose an import commit endpoint or claim Tradovate, MT4/MT5,
TradingView or NinjaTrader format support. Real representative exports are required
before adapter-specific mapping, confirmation and reconciliation can be enabled.

## Acceptance

Retain database/uploads, restart twice, inspect old IDs/notes/images. Log a manual
trade, review broker facts, edit a Playbook answer and date/account Daily Review.
Repeat read-only sync and verify preserved reviews and no duplicates. Test a trade
near midnight across Trades/Calendar/Analysis. Replay a close and repeat its save.
Open Chart at trade or Replay this period from either trades view.
