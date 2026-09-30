# Ledger

Local trading research, charting, causal Replay, backtesting, Journal and investment
Portfolio. Checkpoint 12 is the release-candidate workflow foundation.

## Run locally

### One-command Windows launcher

After the one-time setup below, run `Start-Ledger.bat` (double-click is fine) or `./Start-Ledger.ps1`. It starts both local services and opens the app. See [Running Ledger](docs/RUNNING_LEDGER.md) for private always-on and hosting notes.

### First-time/manual setup

Use Python 3.11+ and Node compatible with the installed Vite version. From `backend`,
create `.venv`, install `requirements.txt` (plus `pytest` for tests), copy `.env.example`
to `.env` and configure only the providers you use. Run:

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

From `frontend`, run `npm ci`, then `npm run dev`. Use one backend process per data
directory; queue ownership, broker scheduling and provider quotas are process-local.
This is a trusted local application, not a hardened multi-user internet service.

## Start Ledger on Windows

After the one-time Python/Node setup, run `Start-Ledger.bat`. Ledger starts the backend and frontend as hidden background processes and opens the browser. Use `Stop-Ledger.bat` to shut them down. For a completely hidden launcher, use `Start-Ledger-Hidden.vbs` and `Stop-Ledger-Hidden.vbs`. Logs are written to `.ledger-runtime`. See [Running Ledger](docs/RUNNING_LEDGER.md).

## Preserve your data

Back up and retain `backend/data` (database, uploads and caches) and `backend/.env`.
Startup migrations preserve existing records. Never replace your database with an
update bundle. Workspace executes explicitly trusted Python; it is not a sandbox.
Broker sync is read-only. No real/demo order execution is implemented.

## Verify

```powershell
powershell -ExecutionPolicy Bypass -File ./Verify-Ledger.ps1
```

This runs backend tests, frontend utility tests and a production build with isolated
output and no dotenv reading. See [verification](docs/VERIFICATION.md) for details
and opt-in browser checks. Never run fixture scripts against the live database.

## Documentation

- [Architecture](docs/ARCHITECTURE.md), [data sources](docs/DATA_SOURCES.md), [running Ledger](docs/RUNNING_LEDGER.md)
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
