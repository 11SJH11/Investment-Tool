# MT5 DEMO automation — implementation status

Updated 29 October 2026. This is the current implementation record for the T02
saved-run deployment brief, not a claim that automated broker execution is ready.

## 29 October: durable session budgets

Native submission now persists its verified worker-supplied session identity in
the write-ahead attempt, and checks the limit again inside that transaction.
Counts span policy/source-version changes for the same account and strategy;
distinct accounts and strategies remain separate. Uncertain/rejected attempts
consume the budget. Attempts with no historical session identity conservatively
count in every session. A new session never releases unresolved broker state.
No existing records are rewritten and no schema migration is required: the
optional session key is stored in the existing attempt JSON document.

Focused session/submission/attempt/reconciliation/ledger suite: **87 passed**,
including 12 new session-budget cases. Frontend: **145 passed**, production build
passed (184 modules; existing chunk-size warning). Mocked browser acceptance passed
at 390/1024/1440/1920. The prior full run ended at 36% without a result and is **not**
counted as passed. The fresh full run completed: **2,163 passed, 41 skipped**, one
existing FastAPI/Starlette deprecation warning, **645.07 seconds**. Log:
`.ledger-test-artifacts/logs/demo-recovery-session-full.log`. `git diff --check`
passed. Skipped opt-in checks and mocked broker fixtures are not genuine Fedora
execution acceptance. No orders or paid model calls were made.

The native boundary now supports durable session counts; the future worker must
derive that identity from verified New York session timing, not a browser input.
The older read-only diagnostic coordinator still counts all historical attempts
conservatively. Neither path grants execution authority.

## 26 October: merged Fedora changes and uncertain stop recovery

Fedora commits `7f6dc4c` and `1ce1e1f` have been merged without replacing local
execution work. User research scripts remain untracked. The sibling import in
`compare_variants.py` was minimally corrected for package discovery while retaining
standalone CLI use; without that correction it prevented backend strategy startup.

`DemoSubmission.recover_protection` can now resolve an uncertain modification from
a fresh complete broker snapshot, including after a Ledger process restart. It
requires receipt-owned entry fills, the original DEMO account, the exact intended
stop/target, no external scale-in and no pending orders. It never sends an order,
retries a modification, clears the account guard or authorizes trading. Separate
account recovery is still required. Closed/absent positions, stale observations,
conflicting ownership and incomplete evidence remain unresolved.

Focused merged-tree tests: **78 passed**, including 11 new recovery cases. Full
merged-tree verification subsequently passed as recorded in the 29 October section.
Frontend tests/build and mocked browser verification passed at
390/1024/1440/1920. No genuine broker execution was performed.

The user will run Fedora acceptance commands; no SSH access was supplied. This
checkpoint does not complete continuous worker authority, lifecycle controls,
coexistence coordination, clock validation, Journal attribution or activation.

## Next checkpoint: guarded native submission and protection

`app/brokers/mt5_demo_submission.py` now implements a separate native submission
boundary. It is not wired into an active worker or public order endpoint. Its
default authorization callback refuses every operation. Tests inject a clearly
mocked authority; this must not be mistaken for production activation.

Implemented and tested locally:

- Existing account guard, full-history recovery snapshot, broker lot/margin checks
  and account-wide risk calculation are reused. Executable quote and identity are
  checked again before submission. An immutable intent is never silently repriced.
- Actual native `order_send` call is behind that boundary, with broker-side SL/TP
  supplied in the request. The ledger writes uncertainty **before** calling it.
- Missing/malformed responses, exceptions, partial fills and rejections retain
  durable uncertainty. Returned native comments/errors are not exposed. No blind
  resend, no claim that a receipt proves protective orders are working.
- Explicit recovery can release the account only after complete, receipt-bound
  positive broker evidence. Missing receipts and external pending orders block it.
  Recovery never arms a deployment.
- Stop tightening uses the receipt's position identifier and fresh native ticket,
  checks canonical fills, current volume/SL/TP, exact DEMO identity, quote freshness,
  tick alignment and broker stop/freeze distance. TP is preserved and SL cannot
  move farther away. Unrelated manual/Telegram scale-in makes ownership ambiguous
  and blocks modification.
- Modification requests are immutable/idempotent, written before native calls in
  `mt5_protection_attempts`, and marked verified only after broker re-observation.
  Unknown modifications remain blocked and are not automatically resent.
- Reconciliation uses a verified tightened stop without rewriting the original
  intent. Restart still fences the old writer and preserves all uncertainty.
- Draft requests explicitly name the intended strategy; selecting a T01 run for a
  T02 deployment is rejected even if both versions are installed and source-valid.

Focused native submission/protection/ledger/reconciliation regression: **87 passed**.
Full native-boundary checkpoint: **2,128 passed / 41 skipped**, one existing
deprecation warning, 591.25s (`demo-submission-full.log`). Frontend **145 passed**;
production build passed (182 modules); mocked browser checks passed at
390/1024/1440/1920, including same-origin API routing. This includes mocked native
calls only. Continuous worker authority, per-session counters (the
submission boundary currently counts historical attempts conservatively), unresolved
closed-position modification recovery, deployment lifecycle and Journal/dashboard integration are
still outstanding. Neither native code nor a mocked passing test grants activation.

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

1. Connect the guarded native submission boundary to an authenticated separate DEMO
   gateway/worker, without adding order methods to read-only bridges.
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

## Read-only Fedora evidence needed for genuine acceptance

No service restart, database migration or order is involved in these checks. On
Fedora, from the current checkout, run:

```bash
cd /home/SJH/Projects/Investment-Tool/backend
.venv/bin/python tools/check_mt5_bridge.py \
  --bridge-url http://127.0.0.1:18765 \
  --token-file "$HOME/.config/ledger-mt5-bridge/token" \
  --symbol XAUUSDs --confirm-demo
```

This existing tool uses a new temporary database, verifies DEMO identity, imports
twice for idempotence, and takes five clock samples. It does not open Ledger's
production DB. Run during an active market for useful moving-tick evidence; a
weekend stale tick cannot establish a current UTC offset. Do not paste token
contents. A newly observed offset alone does not establish all historical DST rules.

For the remote UI error, inspect whether the existing backend service is running
and whether nginx forwards `/api/algo-trading` to it. Share the HTTP status rather
than private environment files. Windows had no running backend at inspection.
The new frontend needs rebuilding on Fedora; an old explicit `VITE_API_BASE_URL`
still overrides the repaired same-origin default. Do not restart production
services as an implicit part of development verification.
