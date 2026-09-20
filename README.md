# Ledger

Local trading research, charting, causal Replay, backtesting, Journal and investment
Portfolio. Checkpoint 12 is the release-candidate workflow foundation.

## Run locally

Use Python 3.11+ and Node compatible with the installed Vite version. From `backend`,
create `.venv`, install `requirements.txt` (plus `pytest` for tests), copy `.env.example`
to `.env` and configure only the providers you use. Run:

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

From `frontend`, run `npm ci`, then `npm run dev`. Use one backend process per data
directory; queue ownership, broker scheduling and provider quotas are process-local.
This is a trusted local application, not a hardened multi-user internet service.

## Preserve your data

Back up and retain `backend/data` (database, uploads and caches) and `backend/.env`.
Startup migrations preserve existing records. Never replace your database with an
update bundle. Workspace executes explicitly trusted Python; it is not a sandbox.
Broker sync is read-only. No real/demo order execution is implemented.

## Verify

```powershell
# backend
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=<fresh-writable-directory>
# frontend
node --test tests/*.test.js
npm.cmd run build
# repository
 git diff --check
```

Use isolated fixture data for browser acceptance; never run test import/review scripts
against your production database. See [release report](docs/RELEASE_CHECKPOINT_12.md)
for exact results, browser setup and remaining limitations.

## Documentation

- [Architecture](docs/ARCHITECTURE.md), [data sources](docs/DATA_SOURCES.md)
- [Charts and drawings](docs/CHART_WORKSPACE.md), [Journal](docs/JOURNAL.md)
- [Backtest workflow](docs/BACKTEST_WORKFLOW.md), [Strategy Workspace](docs/STRATEGY_WORKSPACE.md)
- [Broker connections](docs/BROKER_CONNECTIONS.md), [extension contract](docs/BROKER_EXTENSION_CONTRACT.md)
- [Futures economics](docs/FUTURES_FOUNDATION.md), [continuous methodology and real NQ evidence](docs/CONTINUOUS_FUTURES_RESEARCH.md)
- [Momentum/VCP](docs/MOMENTUM_VCP_BASELINE_V1.md), [ORB/VWAP](docs/ORB_VWAP_BASELINES.md), [Gold variants](docs/GOLD_EXPERIMENTS.md)
- [Release history](docs/RELEASE_CHECKPOINTS.md), [third-party notices](docs/THIRD_PARTY.md)
- [Engineering rules](AGENTS.md), [task workflow](CODEX_WORKFLOW.md)

NQ source/roll provenance is explicit; TradingView parity is unverified. Stock
universes are current-only and historical analysis may contain survivorship bias.
Autochartist remains scaffold-only; no licensed portal scraping is performed.
