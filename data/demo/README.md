# Ledger synthetic demo dataset

`ledger.db` is a deterministic **synthetic** dataset for UI/load testing. It is not market evidence and must not be used to judge a strategy.

It contains roughly three years of weekday Journal activity plus saved research, portfolio activity and a populated Screener universe. The generator is `backend/tools/generate_demo_data.py`.

To use it temporarily from PowerShell without touching your normal data directory:

```powershell
cd backend
$env:LEDGER_DATA_DIR="../data/demo"
python -m uvicorn app.main:app --reload
```

Open a new terminal for your normal Ledger environment afterwards, or run `Remove-Item Env:LEDGER_DATA_DIR` before restarting the backend.

Regenerate it from the repository root with:

```powershell
python backend/tools/generate_demo_data.py --force
```
