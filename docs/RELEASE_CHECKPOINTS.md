# Ledger release checkpoints — 2026-09-16

Baseline: master, commit 7b69031 preserves the previously uncommitted Journal V2
and Momentum/VCP release. Audit baseline: 193 backend tests, 3 Journal utility
tests and frontend production build pass. Two existing backend deprecations.

## Audit and boundaries

Replay currently aggregates the full provider range before slicing its cursor;
the API also returns unrevealed prices. Fix by clipping canonical 1m data before
aggregation and before indicator calculation. Return future timestamps only for
navigation, never future OHLCV. Timestamp-based visible/furthest cursors survive
timeframe changes and saved sessions. Order evaluation uses explicitly revealed
canonical minutes. No normal Charts or BacktestEngine changes in checkpoint 1.

Journal uses one core filter/summary module and JSON Playbook definitions. Extend
that contract with OR within each selected dimension, AND across dimensions,
entry dates in the selected timezone, and currency-separated summaries. Stable
question IDs/answers stay unchanged. Column preferences use browser localStorage.
No checkpoint 1 database/schema migration is needed.

Expected checkpoint 1 edits: backend/app/services/backtest.py,
backend/app/api/strategy_lab.py, backend/app/api/journal.py,
backend/app/core/journal_analytics.py; frontend/src/api/client.js,
frontend/src/features/strategy-lab/ReplayPanel.jsx; JournalFilters.jsx,
JournalShared.jsx, PlaybookView.jsx, TradesView.jsx, JournalPage.jsx under
frontend/src/features/journal; existing Replay tests whose response contract
intentionally changes. New Replay snapshot and Journal option/table helpers,
targeted backend/frontend tests, and this handoff document.

Architecture risks for later checkpoints: Portfolio derives holdings from local
buy/sell events and has no Trading 212 adapter. Provider position snapshots must
not be counted again as historical buys. Additive broker snapshot/import/cursor
storage is expected. OANDA already has atomic idempotent history sync but one
configured profile; retain its identities/reviews while generalizing profiles.
Tradovate must remain explicitly unsupported until a real API contract exists.

Futures currently advertise NQ1!, retain source_contract, and use calendar-front
selection with optional additive adjustment. Instrument metadata/engine lack
contract economics. Verify official family specifications and provider support
before exposing aliases or implementing multiplier-aware generic accounting.
Never guess volume/OI roll schedules or claim TradingView equivalence.

Registry imports Python plugins in-process; Strategy Workspace must not execute
on paste/save, must protect frozen files and label local trusted-code execution.
Saved runs already preserve JSON snapshots and Trade Audit accepts metadata.
New strategy formulas must be documented before coding, with missing DXY data
explicitly unsupported rather than substituted. Gold and Momentum baselines stay
frozen. No new schema is expected for strategy diagnostics/comparison snapshots.

## Checkpoint order and verification

1. Replay + Journal UX — complete; verified and committed separately.
2. Trading 212 + broker abstraction — complete, including multiple profiles and Tradovate scaffold.
3. Futures foundation - complete; dated-contract execution and continuous chart provenance. See `FUTURES_FOUNDATION.md`.
4. Strategy Workspace - complete; trusted explicit subprocess execution. See `STRATEGY_WORKSPACE.md`.
5. ORB + VWAP - complete; see `ORB_VWAP_BASELINES.md`.
6. Gold variants + comparison.
7. Full regression + final release report.

Use synthetic/offline fixtures and temporary DB/uploads. Checkpoint 1 tests cover
partial 5m/15m OHLCV, exact boundaries, rewind/timeframe round trips, causal
indicators, weekends/XAU 24h, Replay-to-Journal idempotency; multi-select filter
combinations, summary denominators/currencies, option IDs/answers and column
preferences. Run full backend, Node utility tests, production build and diff
checks before checkpoint commit. Browser smoke uses an isolated local dataset.
At a capacity boundary, finish and commit the checkpoint, record exact results
and remaining work here, and stop for a later continuation.

## Checkpoint 2 handoff

Completed after checkpoint 1 commit `884de9f`. See [BROKER_CONNECTIONS.md](BROKER_CONNECTIONS.md)
for configuration, official API references, schema, limitations and acceptance checks.
Full backend **260 passed**; frontend utilities **7 passed**; production build passed
(65 modules). Isolated browser sync/re-sync, notes preservation, separate fills and
1024px layout passed. No real credentials or user data were used. Checkpoints 3–7 remain.

Modified files: backend/.env.example; backend/app/api/router.py;
backend/app/brokers/base.py; backend/app/brokers/oanda.py; backend/app/core/config.py;
backend/app/services/container.py; backend/app/storage/database.py;
backend/tests/conftest.py; frontend/src/api/client.js;
frontend/src/features/journal/BrokerSyncPanel.jsx;
frontend/src/features/portfolio/PortfolioPage.jsx;
frontend/src/features/settings/SettingsPage.jsx; docs/RELEASE_CHECKPOINTS.md.

New files: backend/app/api/brokers.py; backend/app/brokers/profiles.py;
backend/app/brokers/trading212.py; backend/app/brokers/tradovate.py;
backend/app/services/broker_connections.py;
backend/app/storage/portfolio_broker_repository.py;
backend/tests/test_broker_connections.py; docs/BROKER_CONNECTIONS.md;
frontend/src/features/brokers/BrokerProfilesPanel.jsx;
frontend/src/features/portfolio/BrokerPortfolioPanel.jsx.

### Checkpoint 3 preliminary inspection (historical audit, superseded by implementation)

Checkpoint 2 commit is `b39daeb`. The next-turn entry point is futures foundation.
Read the original release brief and verify official CME/Massive specifications.
No futures implementation files were changed during this preliminary inspection.

- `backend/app/data/instruments.py` advertises only NQ1! and XAUUSD; its futures
  regex excludes digit-containing roots such as M2K. Add the reusable family
  model with verified economics and provider mappings before advertising aliases.
- `backend/app/backtesting/engine.py` and `models.py` currently assume unit point
  value in sizing, notional exposure, initial risk, partial exits, final P&L and
  unrealized P&L. Any generic extension must default to existing equity/Gold
  behavior and cover all those paths, integer contract sizing and tick handling.
- `backend/app/services/backtest.py` constructs the common engine configuration;
  it must convey verified per-symbol economics, reject unsupported economics,
  and preserve existing strategy rules and market-data routing.
- `backend/app/data/providers/massive_futures.py` uses calendar-front selection
  from provider first/last trade dates and retains source_contract. Its optional
  backward adjustment uses later roll gaps, so research causality and cache
  namespace/provenance require explicit handling. Do not treat continuous roll
  gaps as trading profit or claim a volume/OI schedule without provider evidence.
- Trace `market_store.py`, `market_data.py`, `chart_data.py` and Replay/Journal
  contract accounting before changing metadata; ensure provenance survives the
  actual cache/aggregation path. No change has yet been made to these areas.

Checkpoint 3 is now implemented and verified: 293 backend tests, 10 frontend
utility tests and production build pass. Isolated Chrome verified dated NQ
Replay-to-Journal accounting, continuous order rejection and 1024px layout.
Exact files, formulas, limitations and acceptance checks: `FUTURES_FOUNDATION.md`.
Checkpoint 4 is also complete: 320 full backend tests, 27 focused workspace
cases, 12 frontend utility tests and production build pass. Isolated Chrome
verified static editing/save, explicit execution, saved backtest, built-in
protection, tab persistence, unsaved-navigation guard and 1024px layout.
See `STRATEGY_WORKSPACE.md` for exact files, security boundaries and acceptance.
Checkpoint 5 is complete: 366 full backend tests, 46 focused strategy cases,
12 frontend utility tests and production build pass. Isolated Chrome verified
ORB/research/VWAP runs, saved snapshots, both Trade Audit views, indicator
discovery and 1024px layout. Formulas, exact files, commands and limitations:
`ORB_VWAP_BASELINES.md`. No migration or user-data changes.
Resume at checkpoint 6 Gold variants/comparison, then 7 full release report.
Do not redo checkpoints 1-5. Checkpoint 6 has not been started.


## Checkpoint 1 final handoff

Scope: Replay causality and Journal/Analysis UX only. Baseline snapshot commit
`7b69031` retains the previously completed Journal V2/OANDA and Momentum/VCP work.
Checkpoints 2–7 have not been implemented. Resume with checkpoint 2, using the
original release brief and the architecture audit above. Do not repeat checkpoint 1.

### Implemented behavior

Replay clips canonical one-minute bars at the requested frontier before any
higher-timeframe OHLCV or indicator calculation. At 10:02, a 10:00 five-minute
candle contains exactly the available 10:00, 10:01 and 10:02 bars. The response
marks the frontier candle `is_partial` until the bucket's final minute is revealed.
Future navigation contains timestamps only. `bars` and `source_bars` never include
future prices. The optional timezone-aware `frontier` API argument explicitly
advances or rewinds the snapshot. Visible/furthest cursors are canonical timestamps,
not higher-timeframe indices. One step reveals one available canonical minute;
missing minutes are never fabricated. Order evaluation also uses canonical minutes.
Queued closes and positions survive timeframe switches. Rewind retains review-mode
integrity and blocks new entries until the furthest revealed frontier is reached.
Indicators are invalidated and recomputed at each frontier. Loaded session settings
remain stable until a new replay is loaded. Normal Charts, BacktestEngine, Gold and
Momentum strategy implementations are unchanged from the preserved baseline.

Journal adds separately stored option rows with add/remove/reorder and an explicit
paste helper (newline/comma/slash). Existing option strings are not silently split;
stable question IDs and earlier answers survive option changes. There are 21
selectable table columns, including separate account and environment columns;
preferences persist in localStorage. Twenty-two multi-select dimensions include
the requested structured filters plus result. Values are ORed within a dimension;
dimensions/date bounds are ANDed. Time dimensions use the selected Journal timezone.
Trades, Analysis and Calendar share the backend filter contract. Summaries include
sample N, outcomes, R statistics, currency-separated money, MFE/MAE in R, holding
time, plan adherence and grades. Missing excursions remain unavailable, not zero.
Replay per-share excursions are divided by initial price risk before aggregation;
invalid legacy excursion values are ignored. Plan adherence is Yes divided by
known Yes/No/Partially responses; blank responses are excluded and N is shown.

### Schema and preservation

No database schema or migration changes in this checkpoint. Existing trades,
Playbooks, Daily Reviews, notes, attachments, screenshots and IDs use their existing
storage. Preservation/repeated-initialization tests pass in the full suite. No real
user database, uploads, provider credentials or .env files were edited. The only new
persistent preference is browser-local `ledger.journal.tableColumns.v1`.

### Exact files relative to baseline commit 7b69031

Modified:

- backend/app/api/journal.py
- backend/app/api/strategy_lab.py
- backend/app/core/journal_analytics.py
- backend/app/services/backtest.py (Replay methods only)
- backend/tests/test_phase561_replay_consistency.py
- backend/tests/test_phase56_replay_workspace.py
- frontend/src/api/client.js
- frontend/src/features/journal/JournalFilters.jsx
- frontend/src/features/journal/JournalPage.jsx
- frontend/src/features/journal/JournalShared.jsx
- frontend/src/features/journal/PlaybookView.jsx
- frontend/src/features/journal/TradesView.jsx
- frontend/src/features/strategy-lab/ReplayPanel.jsx

New:

- backend/app/services/replay_snapshot.py
- backend/tests/test_release_journal.py
- backend/tests/test_release_replay.py
- frontend/src/features/journal/OptionEditor.jsx
- frontend/src/features/journal/journalPreferences.js
- frontend/tests/journal.preferences.test.js
- docs/RELEASE_CHECKPOINTS.md

### Verification against checkpoint 1 implementation

Commands run from backend (unique temporary pytest directory each time):

```powershell
.venv/Scripts/python.exe -m pytest -q tests/test_release_journal.py tests/test_release_replay.py -p no:cacheprovider --basetemp "$env:TEMP/ledger-cp1-focused-$([guid]::NewGuid().ToString('N'))"
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp "$env:TEMP/ledger-cp1-full-$([guid]::NewGuid().ToString('N'))"
```

- New focused suites: **39 passed** (26 Journal, 13 Replay), 4.02 seconds.
- Full backend: **232 passed**, 25.66 seconds; two pre-existing dependency
  deprecations (Starlette/httpx and AnyIO BlockingPortal). Includes engine, frozen
  XAU, Momentum, Replay weekends/holidays, OANDA/broker sync, import-order,
  Journal idempotency and migration/preservation regressions.
- Old Replay assertions expecting unrevealed bars/full frontier candles were
  intentionally updated to the new causal response contract.
- New-test development failures were incorrect test invocation/import paths
  (calendar keyword argument and PATCH method), corrected before the green run.
- `node --test tests/journal.test.js tests/journal.preferences.test.js`:
  **7 passed**, 0 failed (4 new preferences/options tests and 3 existing utilities).
- `npm.cmd run build -- --outDir <temporary build directory>`: **passed**, 63
  modules, 1.56 seconds. Smoke-build API base points only to isolated localhost
  port 18082. Existing >500 kB bundle warning remains; no dependency changes.
- `git diff --check`: passed. Verified no changes under backend/app/backtesting,
  normal chart service or normal Charts frontend relative to baseline.

Isolated headless Chrome smoke, synthetic data, temporary SQLite/uploads, provider
network explicitly disabled, viewport 1024 x 900:

- Journal cards (two initial records), all 21 table columns, instrument filter,
  saved columns after navigation and full page reload: passed.
- Cards/table/Analysis document width exactly 1024px; wide table scroll stays
  inside the table container. No page-level horizontal overflow.
- Playbook paste `Aligned / Opposed / Not checked`, reorder, save and backend
  verification of array `[Aligned, Not checked, Opposed]`: passed.
- Replay 10:02 partial 15m/5m volume exactly 123 and high 134 on the synthetic
  fixture; round trip to 1m close 133 preserves frontier: passed.
- Next canonical minute long entry 133, manual next-minute close 134, with the
  queued close surviving a 5m→15m switch; one automatic Journal record: passed.
- Save/resume checkpoint, rewind, timeframe switch preserves review-mode warning
  and disabled entry buttons: passed. No observed application runtime exceptions.
- Temporary smoke evidence: `%TEMP%/ledger-cp1-smoke-ibjlll9c/`, including table
  screenshots and Replay screenshot. Smoke helpers are not production files.

### Limitations and acceptance checklist

- Checkpoint 1 is not the complete major release. Trading 212/multiple broker
  profiles, futures, Strategy Workspace, ORB/VWAP, Gold variants/comparison and
  release-wide final verification remain checkpoints 2–7.
- Older saved Replay checkpoints lack a canonical frontier and cannot safely
  resume; the UI explicitly asks for a new Replay session. Existing Journal
  records and the stored old checkpoint are not deleted by this handling.
- Replay API supports the UI's intraday timeframes (1m through 4h); daily Replay
  requests are rejected instead of bypassing canonical one-minute causality.
- Snapshot requests re-read cached canonical history and recompute indicators on
  each advance. Long horizons/high playback rates have not been load-tested.
  Busy-request guarding prevents overlapping advances; speed is network-bound.
- Future timestamps/session dates remain available for navigation, but future
  OHLCV/indicators do not. This local research tool is not a server-enforced
  adversarial exam: deliberately requesting a later frontier reveals it.
- MFE/MAE are reported only where saved metadata supports R normalization;
  historical records without excursion data remain unavailable.
- Browser checks used deterministic synthetic data, not live broker accounts or
  real provider sessions. Table preferences are browser-local, not cross-device.
- Existing chunk-size and dependency deprecation warnings are unchanged.

Manual acceptance:

1. Start a new Replay session, stop at 10:02, switch 1m→5m→15m→1m. Confirm frontier
   is unchanged and partial OHLCV grows only when new source minutes are revealed.
2. Place a Replay order, advance, queue a close, switch timeframe and advance.
   Review its automatically saved Journal record. Rewind and check integrity label.
3. Add a Playbook choice field; paste/reorder/remove options; save and reopen it.
   Confirm an older linked trade still displays its saved answer.
4. Select Journal Table columns, reload, and confirm preferences persist. Try
   multiple instruments and accounts together; confirm OR-within/AND-across.
5. Check Analysis sample N, missing-excursion counts, timezone-dependent date/hour
   filters and separate currency totals; check Calendar with the same filters.
6. At about 1024px width, verify the page fits and wide tables scroll internally.
