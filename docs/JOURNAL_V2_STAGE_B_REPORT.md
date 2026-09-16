# Journal V2 / OANDA - Task 1 final verification

Task 1 passed its final gate on 2026-09-12, before Momentum/VCP work began. No Journal features were added during this final-verification pass. Tests and browser smoke used temporary data; the user's backend/data and credentials were not used or modified.

## Exact changed files

- `backend/.env.example`
- `backend/app/api/journal.py`
- `backend/app/core/config.py`
- `backend/app/data/http.py`
- `backend/app/services/container.py`
- `backend/app/services/journal.py`
- `backend/app/services/screener.py`
- `backend/app/storage/database.py`
- `backend/app/storage/journal_repository.py`
- `backend/tests/conftest.py`
- `frontend/src/api/client.js`
- `frontend/src/app/App.jsx`
- `frontend/src/features/journal/AnalysisView.jsx`
- `frontend/src/features/journal/CalendarView.jsx`
- `frontend/src/features/journal/DailyReviewView.jsx`
- `frontend/src/features/journal/JournalPage.jsx`
- `frontend/src/features/journal/PlaybookView.jsx`
- `frontend/src/features/journal/TradeDetail.jsx`
- `frontend/src/features/journal/TradesView.jsx`
- `frontend/src/features/journal/journalUtils.js`
- `frontend/src/features/settings/SettingsPage.jsx`

## Exact new files

- `backend/app/brokers/__init__.py`
- `backend/app/brokers/base.py`
- `backend/app/brokers/oanda.py`
- `backend/app/core/journal_analytics.py`
- `backend/app/core/journal_fields.py`
- `backend/app/services/broker_sync.py`
- `backend/app/storage/broker_sync_repository.py`
- `backend/tests/test_broker_sync.py`
- `backend/tests/test_journal_diagnostics.py`
- `backend/tests/test_journal_v2.py`
- `backend/tests/test_oanda_journal_import.py`
- `frontend/src/features/journal/BrokerSyncPanel.jsx`
- `frontend/src/features/journal/ExecutionForm.jsx`
- `frontend/src/features/journal/JournalFilters.jsx`
- `frontend/src/features/journal/JournalShared.jsx`
- `frontend/src/features/journal/ReviewFields.jsx`
- `frontend/src/features/journal/journalTime.js`
- `frontend/tests/journal.test.js`
- `docs/JOURNAL_V2_STAGE_B_REPORT.md` (this report)

## Schema and preservation

Schema version 16 adds Journal Playbook links, setup grade, plan adherence, JSON review answers, account-scoped broker identity, account currency, broker realised P&L, financing, commission, guaranteed fees, dividends, initial risk and cost-completeness fields. Playbooks gain JSON sections and question definitions. A broker_sync_state table stores provider, hashed account/environment identity, cursor, last success and sanitized status/error. No tokens are stored.

Existing daily_reviews and media_attachments columns remain. Legacy freeform fields and attachment slots are retained. Existing source-constraint migration remains preserving: shared rows are copied and checked before its existing table replacement; unknown columns/custom indexes/triggers stop migration instead of discarding them. V2 additions are additive. Repeated initialization is tested. IDs, notes, timeframe notes, source metadata, external IDs, Playbook rules, daily reflections and all attachment ownership/slot records survive the pre-V2 fixture. Playbook deletion clears the link while retaining the trade's custom answers.

Keep the existing backend/data directory, database and uploads when updating. Normal startup applies the migration; no replacement database is supplied. Existing date-only daily reflections remain on their saved date/account when the Journal timezone changes.

## Implemented behaviour

- Trades default to cards, with an optional table, pagination, shared instrument/Playbook/source/account/result/grade/regime/session/date filters and loading/error/empty states.
- Trade detail separates execution from discretionary review. Broker facts are read-only. Manual execution remains editable; Replay uses the same Journal and retains deterministic import identity.
- Review supports configurable grades, plan adherence, market structure/context, setup/shift/relativity, confluences, mistakes, emotions, narrative fields, earlier fields/timeframe notes and every attachment slot. Review-only updates never recalculate broker P&L or replace metadata.
- Playbooks retain old description/rules/checklist/notes and images, add readable/custom sections, and define independent single-choice/multiple-choice/text review questions. Stable field IDs preserve renamed/removed question answers.
- Daily Review loads an exact date/account before editing, shows automatic counts, R, currency totals and distributions, retains freeform/legacy reflections and images, and protects unsaved changes.
- Analysis and Calendar use entry date in one persisted IANA Journal timezone, UTC internally. Win rate uses wins/(wins+losses); breakeven/unknown outcomes are explicit, R sample count is explicit, currency totals stay separate, and infinity is consistently represented. Reports include all matching rows, including beyond the former 5,000-row cap. CSV export includes currencies and provenance.
- Calendar links to the day's trades and Daily Review. Daily Review uses all trades for its selected account, independently of other Calendar filters.
- Settings and Journal distinguish token-only candle capability from token-plus-account Journal history capability. Sync is explicit, with status, masked account/environment, last success and errors. No background history polling.

## Broker implementation and guarantees

The small BrokerHistory protocol/HistoryBatch interface is separate from market-data routing. OANDA uses official account summary, closed trade pages and transaction history. Its transport exposes only GET. There are no broker order/position mutation methods or endpoints. Ledger's local POST sync action performs GET requests to OANDA.

One logical OANDA Trade ID maps to one common Journal row; identity includes provider, environment and hashed account. Partial closes reconcile units and realised P&L, and use their unit-weighted actual fill prices. The original opening fill, closing transaction IDs, underlying reduction fills, historical initial protection and cost metadata are retained. Sync commits all rows and the cursor atomically; failure retains previous rows/cursor. A local lock and database cursor comparison prevent competing syncs from overwriting each other. Resync excludes all discretionary fields and screenshots, and retains the original import metadata.

Incomplete credentials cause zero account-history calls and no adapter construction. Startup and status do not fetch account history. Errors omit request credentials, provider bodies and full account paths. Account labels use a hash prefix. Tests use generated/synthetic credentials only, never real tokens.

Accounting: broker realised P&L + financing + dividends - attributable commission - guaranteed execution fee. Spread is already in executions; halfSpreadCost is metadata only. Missing financing/commission or ambiguous multi-trade fees leave net P&L/result unavailable. Initial stops/targets come only from unambiguous ON_FILL historical protection, never current modified orders or price action. R requires initial stop risk and historical quote-to-home loss conversion when currencies differ; otherwise R is unavailable.

Official contracts checked: [Trade definitions](https://developer.oanda.com/rest-live-v20/trade-df/), [Trade pagination](https://developer.oanda.com/rest-live-v20/trade-ep/), [Transaction definitions](https://developer.oanda.com/rest-live-v20/transaction-df/), [Conversion primitives](https://developer.oanda.com/rest-live-v20/primitives-df/).

## Exact final verification

All pytest commands used `.venv/Scripts/python.exe`, `-q -p no:cacheprovider --tb=short` and a unique `--basetemp` under the system temporary directory. Counts below overlap; they are not additive.

| Check | Result |
|---|---|
| Full backend: `python -m pytest` | **148 passed**, 2 pre-existing deprecation warnings, 13.58 seconds |
| Focused: test_journal_v2.py, test_broker_sync.py, test_oanda_journal_import.py, test_journal_diagnostics.py, test_phase4_journal.py, test_phase6_journal_report.py, test_phase63_journal_research.py | **48 passed**, 2 warnings, 7.49 seconds |
| Explicit import order + test_phase4_migration.py + V2 legacy preservation + unknown-schema guards | **7 passed**, 2 warnings, 2.62 seconds |
| `node --test tests/journal.test.js` | **3 passed**, zero failures |
| `npm run build -- --outDir <unique temporary directory>` | **Passed**, Vite 8.3.0, 61 modules, 1.80 seconds |
| `git diff --check` | Passed |

Full-suite coverage includes existing Replay consistency/integrity, Replay-to-Journal idempotency, BacktestEngine and frozen Gold v1.1 tests. Those implementations and existing tests were not changed for Task 1. Existing deprecations concern Starlette/httpx TestClient and AnyIO BlockingPortal. Vite retains its existing >500 kB chunk warning (675.48 kB JS, 197.21 kB gzip); output is deliberately outside the repo.

Mocked tests cover incomplete credentials, GET-only calls, retry/pagination/high-water mark, identical trade IDs across account/environment identities, duplicate sync, partial closes, home conversion, no inferred stop/R, fee ambiguity, malformed history, atomic rollback, concurrent cursor guard, review preservation, read-only API fields and redaction. Journal tests cover manual execution, custom questions/answers, daily account/date isolation, timezone/DST boundaries, currency separation, >5,000 rows, attachment owner checks, migration and import order.

## Browser checks actually performed

Used local headless Chrome with an isolated temporary profile and a temporary FastAPI database/uploads directory. The server was restarted against the current source for final verification; outbound provider HTTP was disabled. No real broker connection was made. No new browser test dependency was installed.

Passed critical current-tree smoke: cards/table, manual trade creation and saved review, broker review with no objective editor and unchanged 2.10 account-currency P&L, persisted Playbook custom question, saved Daily Review, Calendar-to-Daily Review, Analysis, separate Settings OANDA capabilities, and no horizontal overflow of the main Journal panel at 1024px. Runtime errors: zero. Earlier smoke also exercised date-switch isolation, saved reflection reload, unsaved tab/sidebar guards, and a Replay record in the common Journal. Screenshots at 1440px and 1024px were visually inspected. Temporary harness timing/profile issues were resolved; no unresolved application test failure remains.

## Stage A issues fixed

Broker maths overwriting authoritative P&L; broker objective editing; unscoped new broker identities; hidden report timezone and raw/close-date Calendar grouping; mixed-currency totals, truncated reports and inconsistent denominators/infinity; undefined broker labels; Daily Review retaining another date/account's form; hidden legacy notes/attachment slots; absent Playbook linking/custom review schema; insufficient price-batch diagnostics; bearer/account-path error redaction; deleting attachment files before their owning DB record; missing upload-owner checks. Migration preservation checks were strengthened without a destructive schema redesign. The new storage/service import-order cycle was fixed and explicitly regression-tested.

## Stage A issues deliberately deferred

- **Critical pre-existing Replay risk:** partial higher-timeframe aggregation may expose an already-completed higher-timeframe bar beyond the revealed minute, and Replay responses contain future data before frontend slicing. Existing tests pass but do not prove this known gap is fixed. Replay reveal/fill behaviour is frozen for this task and remains unchanged.
- Chart lifecycle/viewport duplication and PriceChart/ReplayChart/TradeAuditChart consolidation; DrawingOverlay and large Replay/engine files remain unchanged.
- Portfolio pooling of account cost bases, broader market-cache/session/VWAP assumptions, general connection-lifecycle cleanup and unrelated swallowed errors.
- Provider routing, NQ/Massive, Autochartist network/licensing work, strategy tuning and real/demo broker execution.

## Known limitations and assumptions

Only the configured OANDA account is synced, closed trades only. Initial history can be expensive because all transaction ranges and closed-trade pages are read; there is no background job/progress queue. Incremental sync rehydrates trades referenced by new closes/reductions; arbitrary later account adjustments are not a full reconciliation service. A locally deleted broker record is not automatically restored without a later relevant transaction/full history rescan. Older experimental broker rows with unscoped external IDs are not guessed/matched automatically.

Missing optional dividend/guaranteed-fee fields are treated as zero; missing/ambiguous attributable financing or commission suppresses net P&L. Incremental initial-protection hydration checks the opening batch through 20 IDs after its opening fill, so unusual larger batches may leave risk unavailable. This is conservative, not a claim of complete order-modification reconstruction. Provider history that fails reconciliation rejects the whole sync and preserves prior state.

Journal aggregation is uncapped but currently in-memory and may need SQL optimization for very large databases. Recent Daily Review links show the existing 120-row recent list; any specific older date/account remains loadable. There is no statistical significance inference or currency conversion of pooled P&L. Manual price-difference accounting retains its existing asset assumptions; broker accounting is separate. Real-account statement reconciliation, full browser/device coverage and all possible historical broker cost variants remain manual acceptance work.

## Manual acceptance checklist

1. Retain your database/uploads when updating; start Ledger and check existing trade, Playbook, Daily Review IDs, notes and old image slots.
2. Select the Journal timezone; compare a trade near midnight across Trades, Calendar, Analysis and its date/account Daily Review.
3. Log/edit a manual trade; switch cards/table; link a Playbook, add a custom question/answer, save and reload.
4. Change Daily Review date and account; check separate reflections and automatic facts. Test unsaved-change prompts.
5. Without broker credentials, confirm Not configured and normal Journal operation. Token-only should still permit candles while history stays unavailable.
6. With your configured practice account, explicitly sync closed history; compare partial-fill weighted exits, realised P&L, financing/fees and net P&L to OANDA statements. Check unknown initial risk stays unavailable.
7. Add broker notes/grade/tags/images, sync again, and confirm no duplicates or review changes. Check broker execution fields cannot be edited through normal review.
8. Finish a Replay trade and confirm its common Journal record remains idempotent. This does not resolve the deferred Replay reveal risk.
9. Check separate currency totals, custom-field Analysis, Calendar navigation, legacy screenshots and your preferred desktop width/theme.
