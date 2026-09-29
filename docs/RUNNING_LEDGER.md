# Running Ledger

## Normal local use on Windows

After the one-time Python/Node setup, double-click `Start-Ledger.bat` or run:

```powershell
.\Start-Ledger.ps1
```

The launcher starts the FastAPI backend on `127.0.0.1:8000` and the Vite frontend on `127.0.0.1:5173` **in the background**, then opens Ledger in the browser. It does not read, print or modify `.env`. Runtime output is written to `.ledger-runtime/*.log` instead of keeping terminal windows open.

If `frontend/node_modules` is missing, the launcher runs `npm ci`. It deliberately does not create the Python virtual environment automatically because Python versions and provider dependencies should remain an explicit setup choice.

## Keeping Ledger running on your own machine

For normal use, `Start-Ledger.bat` returns after the hidden backend/frontend processes are ready. Run `Stop-Ledger.bat` to stop both process trees cleanly. Double-click `Start-Ledger-Hidden.vbs` / `Stop-Ledger-Hidden.vbs` if you also want the launcher itself to have no visible console flash. If startup fails, use `Start-Ledger.bat` so the error is visible and inspect `.ledger-runtime/backend.err.log` and `.ledger-runtime/frontend.err.log`.

For a trusted personal machine, Windows Task Scheduler can launch `Start-Ledger.ps1` at sign-in. The current launcher still uses the Vite development server, so it is intended for personal use rather than a public service.

Keep one backend process per Ledger data directory. Broker schedulers, backtest queue ownership and provider rate limits are process-local.

## Private always-on access

Ledger is currently a trusted local application, not a hardened multi-user web service. If you want access from another device, prefer a private network such as Tailscale rather than exposing Ledger directly to the public Internet.

For a more permanent private deployment:

1. Run the backend under a service/process manager.
2. Build the frontend with `npm run build`.
3. Serve `frontend/dist` with a static web server.
4. Set `VITE_API_BASE_URL` when building if the backend is not available at `http://localhost:8000/api` from the browser.
5. Put both services behind private-network access or proper authentication/TLS before allowing remote users.
6. Back up `backend/data` and `.env` separately.

Public hosting should wait until authentication, authorization, CSRF/origin policy, secrets management, upload hardening, per-user data isolation and production observability have been designed and tested.
