# MT5 distributed research phase — 18 October 2026

Branch: `feature/mt5-distributed-research`. Base: `0cf9f89dd443180bda19c8f7a46e0be07332a187`.
Worktree: `C:/Users/jamie/Project/Ledger-mt5-research`.
Stable checkout: `C:/Users/jamie/Project/Investment-Tool`, master, untouched.
Its modified tracked `.env` and all untracked strategy/research files are preserved.
No credential values were inspected. The inherited tracked `.env` is removed from
this branch only; the local ignored replacement contains isolation settings only.
This does not purge historical Git secrets or change the original checkout.

## Isolation and startup

- Separate `backend/.venv`; no dependency installs in the original checkout.
- Backend: `backend/.venv/Scripts/python.exe -B tools/run_isolated.py` from this root.
- SQLite, market cache and research state: `.ledger-runtime/data` under this tree.
- Optional credentials belong only in ignored `.ledger-runtime/providers.env`.
  The launcher clears inherited Settings environment fields before reading this
  file and enforces the isolated data root. No credentials are copied automatically.
- Backend listens on localhost:8012; frontend uses port 5174 with
  `VITE_API_BASE_URL=http://127.0.0.1:8012/api`.
- Workspace source files resolve to this worktree's strategies directory.
- No shared runtime/cache directory and no database migrations against master.
- Tests use new temporary databases. Do not copy the stable SQLite database.
- Never merge automatically. Review commits then merge explicitly from master.

## Relevant existing capabilities

MT5 already supports read-only Journal imports and explicitly mapped, verified
NQ/MNQ futures bars, with account-isolated caching and CFD rejection. It does not
yet provide generic TradeQuo discovery/ticks/coverage or Strategy Tester execution.
Reuse its process-global terminal lock and identity checks; do not create a second
terminal session system. Existing canonical results/export/research governance
must be audited before extensions. No terminal execution/parity claims yet.

## Order

Follow the requested 17 stages. Stage 1 isolation is implemented. Stage 2 starts
with actual broker symbol metadata; futures verification remains a distinct path.
Stages 3–17 remain pending. MT5 distribution must remain disabled until actual
Ledger/MQL5 decision/state parity is demonstrated, not merely fixture P&L similarity.

Official references: [MT5 symbols](https://www.mql5.com/en/docs/python_metatrader5/mt5symbolsget_py),
[MT5 ticks/UTC](https://www.mql5.com/en/docs/python_metatrader5/mt5copyticksrange_py),
[Robinhood external agents](https://robinhood.com/us/en/support/articles/onboarding-an-external-agent/).
Robinhood registration/auth prerequisites still require investigation; no unofficial
API or token extraction fallback is authorized.
