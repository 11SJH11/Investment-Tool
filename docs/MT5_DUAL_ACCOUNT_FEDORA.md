# Dual MT5 accounts on Fedora

Branch: `feature/mt5-demo-execution`. This adds a second **read-only** bridge;
it does not enable automated trading. Fixture verification is complete as recorded
below; installation and genuine LIVE acceptance on Fedora remain operator steps.

## Deploy after logging into KDE

Run as your normal desktop user, not root:

```bash
cd ~/Projects/Investment-Tool
git branch --show-current
git pull --ff-only origin feature/mt5-demo-execution
bash deploy/setup-mt5-live-bridge.sh --check
bash deploy/setup-mt5-live-bridge.sh --install
bash deploy/setup-mt5-live-bridge.sh --validate
```

Check the displayed branch is `feature/mt5-demo-execution` before pulling. Resolve
any local changes normally; do not reset them. The installer requires existing
`~/.mt5-live`, a logged-in LIVE terminal, Windows Python 3.11 in that prefix, Wine,
`ss`, systemd, and Ledger's existing `backend/.venv/bin/python`.
`--check` checks files only; `--install` performs actual native-package and LIVE
identity checks. It never supplies a login/password or switches terminal accounts.

If Windows Python is missing, run the official Python 3.11 Windows installer with
`WINEPREFIX="$HOME/.mt5-live" wine /path/to/python-3.11.9-amd64.exe` and install
for the current Wine user. Then install the official integration in that Python:

```bash
WINEPREFIX="$HOME/.mt5-live" wine "/path/inside/.mt5-live/to/Python311/python.exe" -m pip install MetaTrader5==5.0.6231
```

Use actual executable paths. If several terminals/Pythons exist, pass
`--windows-python /absolute/path/to/python.exe --terminal /absolute/path/to/terminal64.exe`
to each installer invocation. Paths outside the LIVE prefix are rejected.

The guided installer asks you to confirm the masked account identity and server.
It writes private configuration/token and a minimal standalone bridge runtime in
`~/.config/ledger-mt5-live-bridge/`, installs the LIVE user service, starts it,
checks loopback-only listening, and imports twice into a **new temporary database**.
Acceptance sends no orders and never opens the production Ledger database.
Only after acceptance does it register the profile and offer login startup.
If acceptance fails, a newly started bridge is stopped; an existing service is
preserved. A restarted existing LIVE bridge remains available for investigation.

## Accounts and service boundaries

| Profile | Environment | Prefix | Port | Service |
| --- | --- | --- | --- | --- |
| `mt5-default` | DEMO | `~/.mt5` | 18765 | existing `ledger-mt5-bridge.service` |
| `mt5-live` | LIVE | `~/.mt5-live` | 18766 | new `ledger-mt5-live-bridge.service` |

Each bridge pins login, server and account trade mode. Reads check identity before
and after native calls. LIVE requires explicit LIVE protocol requests; legacy DEMO
requests remain compatible. Independent tokens, literal loopback binding, method
allowlists, response limits and watchdogs apply. No order placement, modification,
cancellation or account-login method is exposed. Bridge profiles cannot change
environment through saved Settings preferences. Account keys already include
provider/environment/server/login; identical tickets do not collide across accounts.

The installer adds `BROKER_PROFILES_FILE` through a new backend systemd drop-in.
This private JSON array is additive to existing defaults and `BROKER_PROFILES_JSON`.
It does not edit `.env`. Duplicate IDs fail closed. Identical reruns are no-ops;
changed managed files are backed up where replacement is explicitly supported,
and conflicting config/unit files are refused. An existing different profile-file
overlay or conflicting systemd override requires manual integration: preserve that
file and merge the new profile into it rather than replacing it with this installer.

User-service backends need no root. System-service backends require confirmation
and sudo only to create a new, atomic, exclusive drop-in and reload systemd.
The backend is **never restarted automatically**. Finish running research jobs,
then use the appropriate command for your existing service:

```bash
# User service (only if this is how your backend already runs):
systemctl --user restart ledger-backend.service
# OR system service:
sudo systemctl restart ledger-backend.service
```

The accepted LIVE profile is enabled after that restart. Existing backend scheduling
defaults to read-only auto-sync; Settings can disable or configure it. In Settings,
verify both profiles, use Test/discover, confirm account identity, and Sync now.
Journal account/environment filters separate imports. Notes, reviews, screenshots,
partial-close reconciliation and history use the existing canonical Journal path.
Sync failure preserves previous records and cursor. Disconnect does not delete history.

## Startup, verification and troubleshooting

```bash
systemctl --user status ledger-mt5-live-bridge.service
ss -ltn 'sport = :18766'
bash deploy/setup-mt5-live-bridge.sh --validate
```

The generated unit is tied to `graphical-session.target`, not headless boot.
After a reboot, log into KDE. It initializes the exact LIVE terminal path; it
does not use whichever terminal happens to be the system default. Existing DEMO
and Telegram startup are untouched. Restart policy is 10 seconds with a three-start
limit in five minutes. Native hangs terminate only this bridge process. Ordinary
read failures leave the service available for a later sync retry.

For failure diagnostics, inspect the LIVE service locally. The installer suppresses
raw subprocess output to avoid exposing account credentials. Occupied port,
wrong account, missing package, ambiguous executable, conflicting profile or
override, missing graphical session, and failed temporary-DB imports stop acceptance.
Do not bypass identity failures. If the LIVE broker uses a different Gold symbol
than `XAUUSDs`, the acceptance helper's `--symbol` option supports it; the guided
installer currently uses `XAUUSDs`, and will refuse acceptance rather than invent
symbol mapping. A new fill between the two acceptance syncs can legitimately
require rerunning acceptance during a quiet period.

Timestamps remain explicitly `unverified`. Journal retains the adapter's current
raw broker-history convention; this release does not prove those timestamps are
UTC. Tick diagnostics report observed offsets, not a verified seasonal schedule.
Historical market-data/research calls requiring UTC remain blocked. No permanent
UTC+3 conversion or automatic-execution authorization is introduced.

## Safe rollback

1. In Settings disable auto-sync for `mt5-live`; let any current sync finish.
2. `systemctl --user disable --now ledger-mt5-live-bridge.service` affects only LIVE.
3. Remove only the generated `90-mt5-live-profile.conf` backend drop-in after
   inspecting it, reload the corresponding systemd manager, and restart the
   backend at a planned quiet point. Keep private configuration/backups for recovery.
4. Do not remove the database, `.env`, DEMO service/prefix or Telegram project.
   Historical LIVE Journal entries and annotations remain in Ledger.

## External execution safety

The Telegram repository is not available in this Windows checkout and was not
audited or modified. Its own execution client must pin DEMO login, server and
trade mode before every order and fail closed after any identity change. Ledger's
read-only allowlist does not protect a separate bot's native MT5 execution calls.
Real Fedora services, reboot/login recovery and production Journal acceptance
must be checked on Fedora; mocked tests do not establish those facts.

## Verification and changes

No database schema migration. New configuration: optional `BROKER_PROFILES_FILE`.
Final verification (25 October 2026): full backend **2,075 passed, 41 skipped**
in 625.13 seconds; focused broker/deployment suite **80 passed** (a subset of the
full run); frontend **145 passed**; production build passed (180 modules).
Existing Starlette/httpx deprecation and large-chunk build warnings remain.
Mocked broker UI passed at 1024/1440/1920px, including simultaneous locked DEMO/LIVE
profiles; Research Agent diagnostics passed at 390/1024/1440/1920px and after reload.
No browser runtime errors. `git diff --check` passed. These are local fixture
checks, not genuine Fedora LIVE acceptance. The opt-in skipped checks were not
represented as passes.

Tests cover independent HTTP bridges, separate tokens/ports, identity failures,
rejected trading APIs, same-ticket Journal isolation, repeat sync, failed LIVE sync,
profile locking and atomic/idempotent deployment files.

Changed application files: bridge server/client, broker profiles, settings,
broker-connections service, BrokerProfilesPanel, `.env.example` and the existing
read-only acceptance helper. New files: installer shell/Python scripts,
`test_mt5_dual_bridge.py`, `test_mt5_live_deploy.py`, and this guide. The installer
generates `ledger-mt5-live-bridge.service` from its tested `unit()` template.

Exact dual-account checkpoint file list:

```text
.env.example
README.md
backend/app/brokers/mt5_bridge_client.py
backend/app/brokers/mt5_bridge_server.py
backend/app/brokers/profiles.py
backend/app/core/config.py
backend/app/services/broker_connections.py
backend/tests/test_mt5_bridge.py
backend/tests/test_mt5_dual_bridge.py (new)
backend/tests/test_mt5_live_deploy.py (new)
backend/tools/check_mt5_bridge.py
deploy/setup-mt5-live-bridge.sh (new)
deploy/setup_mt5_live_bridge.py (new)
docs/MT5_DUAL_ACCOUNT_FEDORA.md (new)
docs/MT5_LINUX_BRIDGE.md
docs/README.md
docs/UNIFIED_DEVELOPMENT_2026-10.md
frontend/src/features/brokers/BrokerProfilesPanel.jsx
frontend/tests/browser/broker-connections.mjs
frontend/tests/browser/campaign-progress.mjs (reload readiness test repair)
```
