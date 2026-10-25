# MT5 DEMO automation — implementation status

Updated 25 October 2026. This is the current implementation record for the T02
saved-run deployment brief, not a claim that automated broker execution is ready.

## Verified checkpoint: immutable drafts and decision parity

- T01 and T02 reuse the canonical frozen Gold strategy through the existing
  completed-bar runtime. T02 ratio acceptance/rejection, first setup consumption,
  DST session dates and completed-minute breakeven timing have engine parity tests.
- Saved-run drafts require a single-symbol 1m T01/T02 run, matching strategy key,
  installed implementation fingerprint and verified source archive. Saved results
  are never rewritten. A changed implementation requires a matching new backtest.
- Only an enabled, selected MT5 DEMO profile with a recorded matching DEMO account
  observation and exact discovered XAU/USD broker symbol qualifies. LIVE is rejected
  by the backend. Profile changes during preparation invalidate the request.
- Suggested configurable risk is 0.5% and daily loss is 2%. Exposure must be entered
  explicitly. Risk estimates use timestamped recorded equity, not a trade guarantee.
- Frozen session and strategy rules stay fixed. Direction is the supported override.
- Draft creation is idempotent and immutable; stored definition hashes are verified.
  `mt5_algo_deployments` is created only by explicit draft creation. GET/preview do
  not migrate the DB. No existing run, Journal or account tables are rewritten.
- Deployment endpoints require a separate `MT5_ALGO_CONTROL_TOKEN` of at least
  32 characters, HTTPS remotely, and an allowed Origin. This is a single-operator
  boundary, not multi-user ownership. The form keeps its token in memory only.
- Browser draft controls are clearly unarmed. They do not start a worker or submit
  orders. Existing read-only bridges remain unchanged.

The runtime implementation fingerprint changed. Existing diagnostic streams with
the old fingerprint must be explicitly recreated; they are not silently resumed.

## API connectivity repair

Windows inspection found no backend listener on 8000/8001 or Vite on 5173/5174.
Only the isolated test frontend was listening on 19441. Separately, the frontend
defaulted to `http://localhost:8000/api`, which targets the viewing device when
Ledger is used remotely. It now defaults to same-origin `/api`; Vite proxies `/api`
and `/uploads` to local port 8000. An explicit build-time `VITE_API_BASE_URL` still
takes precedence. Fedora nginx must proxy `/api` to its running Ledger backend.
No production backend was started or restarted as part of this repair.

## Fedora installer safety

`deploy/install_algo_worker.py` is an installer/updater foundation for standalone
workers that accept `--config` and `--state-directory`. It deliberately refuses the
current non-CLI diagnostic class as a deployable worker. The actual execution
worker entry point is still outstanding; do not substitute another module just
to get installation to pass.

- Plan only by default. `--install` is explicit rollout consent.
- Only `ledger-algo-<name>.service`; cannot replace unrelated units. Replacing its
  own unit requires `--replace` and creates a timestamped backup.
- Refuses to update an active worker. Never starts, stops, enables or restarts any
  service. Only queries its named unit and calls user-manager `daemon-reload`.
- Never runs git, pip, database initialization/migrations, or imports worker code.
  Never reads the backend `.env`. A dedicated private config is required.
- Worker state must be outside the repository, new/empty or already marked by this
  installer. Existing production data directories cannot be adopted automatically.
- Generated unit has no Telegram/bridge/backend dependencies, uses read-only system
  and home paths with its own state directory writable, and has automatic restart
  disabled pending verified recovery. Native Fedora sandbox acceptance is pending.

`daemon-reload` reloads manager configuration rather than restarting applications:
[systemctl documentation](https://www.freedesktop.org/software/systemd/man/latest/systemctl.html#daemon-reload).
Filesystem protections in user services depend on namespace support; the unit
requests `PrivateUsers=true`. Verify the effective sandbox on Fedora before rollout:
[systemd execution documentation](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html#Sandboxing).

Installer interface (not an activation command; runnable worker still pending):

```bash
python3 deploy/install_algo_worker.py --help
# Once a verified worker exists: supply --root, --name, --module, --config,
# --state-directory. Inspect the plan, then add --install for approved rollout.
# Updating also requires --replace and an explicitly stopped worker.
```

Roll back only the new worker's unit from its timestamped backup and reload the
user manager. Do not roll back or replace the Ledger database. Stopping a future
execution worker requires reviewing broker-side protection first.

## Verification

- Full backend: **2,104 passed, 41 skipped**, one existing FastAPI/httpx deprecation,
  591.48s. Log: `.ledger-test-artifacts/logs/t02-drafts-full.log`.
- Focused T01/T02/runtime/poll/worker/drafts: 46 passed before two additional draft
  integrity/account-race tests; both additional tests are included in the full run.
- Installer/draft focused run: 13 passed before those two additional tests.
- Frontend: 145 tests passed; production build passed, 182 modules, existing chunk
  size warning. Same-origin routing repair is reverified at checkpoint closeout.
- Mocked browser: draft validation/save, DEMO-only selection, memory-only token,
  form closure clearing, no activation calls, no page overflow at 390/1024/1440/1920.
- No genuine broker orders, paid model calls or production DB/service changes.

## Remaining implementation — do not call this complete

1. Separate DEMO execution gateway, without adding order methods to read-only bridges.
2. Persistent worker wiring: fresh completed bars, risk reservation, broker submission,
   protective SL/TP, partial/unknown receipts, owned position management and recovery.
3. Persisted Pause/Resume/Stop, authenticated activation and restart reconciliation.
4. Verified broker timestamp interpretation and seasonal transition handling.
5. Account-wide risk including Telegram/manual activity; block unsafe coexistence.
6. Receipt-based Journal attribution and measured per-deployment statistics/dashboard.
7. Standalone worker CLI, Fedora sandbox/install acceptance, genuine DEMO smoke test.

The user has now explicitly requested activation of DEMO trading. This authorizes
the objective; it does not establish that the technical acceptance gates passed.
Do not activate the Windows LIVE profile. No Fedora SSH access is configured;
the user previously elected to run Fedora acceptance commands. Timestamp seasonal
rules and independent broker/protection acceptance remain outstanding.
