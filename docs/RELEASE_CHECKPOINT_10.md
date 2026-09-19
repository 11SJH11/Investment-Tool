# Checkpoint 10 — functional stabilisation

Checkpoint 11 remains gated on the completed verification recorded below.

## NQ1! diagnosis and remedy

Official references: [Massive contract reference](https://massive.com/docs/rest/futures/contracts), [futures aggregates](https://massive.com/docs/rest/futures/aggregates), and [futures plans](https://massive.com/futures).

The contracts endpoint without `date` returns historical daily snapshots, not a unique contract directory. A real NQ request returned 1,000 rows, repeated NQH5 records and another page. Adding a point-in-time date and `type=single` returned 13 unique contracts in one page. The previous implementation paginated the wrong dataset and exhausted the reference budget.

Discovery now requests dated monthly snapshots spanning the requested range, deduplicates contracts, and persists them separately from OHLCV. A new cache namespace avoids reusing the earlier erroneous lookup/cooldown. Every date/expiry comes from Massive; no synthetic contract calendar or bars are introduced. All Massive endpoint calls share a per-key process budget, default five requests/minute, plus bounded Retry-After recovery. Set MASSIVE_CALLS_PER_MINUTE only to a rate supported by your subscription. Long historical cold loads still take time on restricted plans. Other applications using the same key can consume its quota.

Massive remains the selected provider. The real access tested was sufficient; no provider switch was necessary. If entitlement later proves insufficient, Databento's CME historical data and continuous-symbol mapping is a documented alternative requiring a separate integration, subscription and comparison. No automatic fallback or claim of equal data has been added.

Real read-only checks used isolated data/cache directories, never the user's Ledger database:
- September 1, 2026: 1m/5m/15m/1h bars, source NQU6. ORB produced two raw dated-contract fills with $1,000,000 test capital and one-contract sizing. Engine economics remain tick .25, tick value $5, point value $20.
- September 18, 2026: 1,150 / 231 / 77 / 20 bars at the respective timeframes, source NQZ6.
- September 10–18: old contract NQU6, transition at the September 15 evening session boundary, new NQZ6 thereafter. UTC dates can contain both contracts around an evening session boundary.
- Browser Charts loaded all four timeframes from exported real provider frames. Browser Replay placed and manually closed a simulated NQ trade; Journal retained NQ1!, NQU6, raw adjustment and roll-version metadata.
- Frozen roll guards continue to reject open-position transfer and cancel stale pending orders; no artificial roll-gap P&L is introduced.

TradingView CME_MINI:NQ1! parity remains unverified: no comparable export was provided. Existing roll/source provenance and comparison workflow remain available. No claim covers every date, provider outage, entitlement or live quote stream.

## Workflow changes

Workspace: save an underscore-prefixed draft, acknowledge trusted Python execution, then Activate strategy. Activation reruns syntax/interface/tests, requires a unique key, atomically promotes a discoverable module, and refreshes the Backtest selector. Source SHA-256/version are retained in immutable history and saved runs. Deactivate removes the promoted module and registry entry while retaining source/history. Built-ins cannot be overwritten. Active drafts can be revalidated in a disposable worker. Trusted Python is not a sandbox.

Backtest is the normal workflow. Validation & out-of-sample and Sensitivity analysis are independent expandable research sections. Auto split 60 / 20 / 20 remains chronological; engine and experiment semantics are unchanged.

Broker scheduling: backend lifecycle owns the schedule, with persisted app_settings preferences/cooldowns, OANDA minimum/default 60s and Trading 212 300s. Configured supported profiles are enabled by default; incomplete profiles make no calls. Manual Sync now remains. Same-profile active/pending work cannot overlap; OANDA additionally locks by account/environment. Provider 429s defer to the scheduler and honor Retry-After. Failures retain last successful data. Normal browser navigation has no effect on scheduling. The browser polls status only. Run one Ledger backend process: distributed/multi-worker scheduling is not implemented.

Activity: explicit provider BUY/SELL and supported Deposit/Withdrawal/Interest/Dividend/Fee directions are visible. Missing/ambiguous action or transfer direction stays Unavailable rather than being guessed from quantity sign.

No schema migration: scheduler state uses existing app_settings. Broker identities, Journal facts/reviews and Portfolio review records are unchanged.

## Verification

Final counts are recorded in the handoff after the last regression run. Browser acceptance used an isolated database and synthetic GET-only OANDA/Trading 212 adapters; live broker accounts were not synchronized. Both backend schedules dispatched without pressing Sync. Portfolio notes survived repeated automatic reconciliation. Workspace activation immediately appeared in the actual Backtest selector and deactivation removed it. Real cached NQ Charts/Replay checks had no JavaScript runtime exceptions.

Manual acceptance: restart the backend; select NQ1! in Charts and Replay; inspect source/roll provenance; use sufficient unleveraged capital for NQ backtests; activate a trusted tested draft; observe it in Backtest; inspect provider auto-sync status and intervals; confirm BUY/SELL and cash labels, and retained reviews. A cold restricted-plan load may wait for the provider budget. Keep the user's existing backend/data and .env.

Final gate: `cd backend; .venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider --basetemp=C:/Users/jamie/Project/cp10-gate`: **477 passed**, two existing deprecation warnings. `node --test tests/*.test.js`: **34 passed**. `npm.cmd run build`: **passed**, 79 modules, existing >500 kB bundle warning. `git diff --check`: **passed**. Checkpoint 11 may now start.

Changed files:

- `backend/.env.example`
- `backend/app/api/brokers.py`
- `backend/app/api/strategy_workspace.py`
- `backend/app/backtesting/strategies/registry.py`
- `backend/app/backtesting/workspace_worker.py`
- `backend/app/brokers/base.py`
- `backend/app/brokers/oanda.py`
- `backend/app/brokers/trading212.py`
- `backend/app/core/config.py`
- `backend/app/data/http.py`
- `backend/app/data/providers/massive_futures.py`
- `backend/app/main.py`
- `backend/app/services/backtest.py`
- `backend/app/services/broker_connections.py`
- `backend/app/services/broker_sync.py`
- `backend/app/services/container.py`
- `backend/app/services/market_data.py`
- `backend/app/services/strategy_workspace.py`
- `backend/tests/test_broker_connections.py`
- `backend/tests/test_massive_reference_cache.py`
- `backend/tests/test_oanda_journal_import.py`
- `backend/tests/test_phase62_multi_asset.py`
- `backend/tests/test_strategy_workspace.py`
- `frontend/src/api/client.js`
- `frontend/src/features/brokers/BrokerProfilesPanel.jsx`
- `frontend/src/features/portfolio/BrokerPortfolioPanel.jsx`
- `frontend/src/features/portfolio/brokerPortfolioUtils.js`
- `frontend/src/features/strategy-lab/StrategyLabPage.jsx`
- `frontend/src/features/strategy-lab/StrategyWorkspace.jsx`
- `frontend/src/features/strategy-lab/ValidationPanel.jsx`
- `frontend/tests/brokerPortfolio.test.js`

New files:

- `backend/app/data/massive_request_gate.py`
- `backend/app/services/broker_scheduler.py`
- `backend/tests/test_broker_scheduler.py`
- `backend/tests/test_massive_snapshot_discovery.py`
- `docs/RELEASE_CHECKPOINT_10.md`
