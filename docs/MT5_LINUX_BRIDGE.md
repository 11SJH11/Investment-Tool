# Read-only MT5 bridge on Fedora / Wine

Status: implemented and fixture-tested; the user reports the DEMO bridge working.
For the new separate LIVE read-only instance, use [dual-account Fedora deployment](MT5_DUAL_ACCOUNT_FEDORA.md).
Existing terminal connectivity
evidence (official MetaTrader5 5.0.6231, Windows Python 3.11.9, shared `~/.mt5`
prefix, TradeQuo DEMO quotes) is useful but is not Ledger acceptance.

The native Linux backend uses the existing MetaTrader5History adapter through an
explicit module facade. Blank MT5_BRIDGE_URL retains Windows-native behaviour.
Account keys, full-position reconciliation, incremental cursor overlap and Journal
idempotency remain canonical. There is no new schema or migration. Do not change
a LIVE profile to point at this demo service; LIVE requires its own explicitly
configured bridge, prefix, token and port.

## Safety and supported operations

- Fixed authenticated JSON API, literal IPv4 loopback binding, exact Host check,
  no CORS, Origin rejection, no redirects/proxies, no pickle or arbitrary RPC.
- Account and terminal facts, symbols, metadata, raw ticks, positions, pending
  orders, historical deals/orders. Symbol selection can only enable visibility.
- One server dispatch at a time; a 60-second exclusive session lease; pinned demo
  login/server checked before and after every native read. Changed identity or
  disconnection fails the read. No credentials cross the transport.
- 16 KiB requests, 32 MiB responses, 100,000-row cap, bounded date requests,
  five-second socket timeout, 35-second authenticated request watchdog. A hung
  native call terminates only the bridge process; the user service restarts with
  backoff. Client timeout is 40 seconds, with no automatic request retry.
- Account identity is returned only over authenticated loopback to preserve the
  adapter's opaque hash calculation. HTTP logging is disabled; public Ledger
  account discovery still returns opaque account keys, not login credentials.
- No order_send, login, modification, cancellation, order_check, margin/profit
  calculation or automation endpoints. Unsupported module operations fail.
- Existing synchronous FastAPI broker endpoints run outside the async event loop.
  Startup/status does not contact the bridge or import the Windows MT5 extension.
- The service explicitly permits initialize against a configured terminal path,
  without login/password parameters. Start the correct demo terminal yourself
  first. MT5 initialize can launch that configured terminal if absent; the
  explicit allow_initialize setting acknowledges this behaviour. It does not
  authorize switching accounts or trading. Identity is verified before reads.

This is a local authenticated service, not a remote broker API. Never expose its
port through Nginx, Meshnet, a tunnel, container publishing or firewall forwarding.
Same-user malicious processes with access to the private token are outside this
boundary. Wine/systemd resource compatibility requires actual Fedora acceptance.

## Time interpretation

No three-hour correction is applied. `tick_diagnostics` records raw milliseconds,
receipt bounds in UTC and their difference. A weekend or disconnected/stale quote
cannot prove clock offset. The supplied single value 1792719348844 alone cannot
establish freshness, a seasonal schedule or historical timestamp semantics.

[Official MT5 documentation](https://www.mql5.com/en/docs/python_metatrader5/mt5copyticksrange_py)
states tick/bar timestamps are UTC. The observed approximately +3h discrepancy
therefore remains installation/broker-specific and unresolved. Record several
advancing quotes during an open market against a synchronized host clock, and
compare dated bars across the relevant DST transitions with independent verified
UTC evidence. Do not infer US or European transition dates from one sample.

Default timestamp_policy is `unverified`: candle/tick-history methods are
implemented but reject research retrieval with timestamp_unverified. Set
`verified_utc` only if both returned history and request boundaries are verified
as UTC. Server-aligned historical time is **not supported by guessing an offset**;
a separately verified historical conversion contract would be required.
Journal history keeps the existing adapter's raw timestamp interpretation and
bounded clock-skew diagnostics; bridge transport does not correct old records.
Treat session/time-of-day analysis of those imported records as unverified until
the broker convention is resolved. Automated execution remains disabled.

## Fedora installation (run as the desktop user)

The existing Wine prefix and demo terminal must already work. Do not reinstall or
replace the prefix. Adapt REPO to the existing checkout; no database is opened by
these installation steps. Python examples below create only private bridge files.

```bash
sudo dnf install wine python3 python3-pip iproute
export REPO="$HOME/Investment-Tool"
export WINEPREFIX="$HOME/.mt5"
cd "$REPO"
git status --short
# Inspect candidates; select your already verified Windows Python and terminal.
find "$WINEPREFIX/drive_c" -iname python.exe -o -iname terminal64.exe
read -r -p 'Full Unix path of the verified Windows python.exe: ' WINE_PYTHON
read -r -p 'Full Unix path of the existing demo terminal64.exe: ' MT5_TERMINAL_UNIX
export WINE_PYTHON MT5_TERMINAL_UNIX
wine "$WINE_PYTHON" -c 'import sys,MetaTrader5 as m; print(sys.version); print(m.__version__)'
# Expected Windows Python 3.11.9 and MetaTrader5 5.0.6231.
# Only if that official package is missing from this exact Python:
# wine "$WINE_PYTHON" -m pip install MetaTrader5==5.0.6231

umask 077
mkdir -p "$HOME/.config/ledger-mt5-bridge" "$HOME/.config/systemd/user"
python3 - <<'PY'
import getpass,json,os,secrets,subprocess
from pathlib import Path
root=Path.home()/'.config/ledger-mt5-bridge'
token=root/'token'
if not token.exists(): token.write_text(secrets.token_hex(32))
token.chmod(0o600)
wp=lambda p:subprocess.check_output(['winepath','-w',str(p)],text=True).strip()
config=dict(environment='demo',allow_initialize=True,
 expected_login=int(getpass.getpass('Expected DEMO account login (not a password): ')),
 expected_server=input('Exact DEMO account server: ').strip(),
 terminal_path=wp(os.environ['MT5_TERMINAL_UNIX']),token_file=wp(token),
 port=18765,timestamp_policy='unverified')
path=root/'config.json'
if path.exists(): raise SystemExit('Existing config retained; review it privately instead of overwriting')
path.write_text(json.dumps(config,indent=2));path.chmod(0o600)
(root/'service.env').write_text('WINE_PYTHON='+json.dumps(os.environ['WINE_PYTHON'])+'\nBRIDGE_CONFIG_WINDOWS='+json.dumps(wp(path))+'\n')
service=(Path(os.environ['REPO'])/'deploy/ledger-mt5-bridge.service').read_text()
service=service.replace('WorkingDirectory=%h/Investment-Tool/backend','WorkingDirectory='+str(Path(os.environ['REPO'])/'backend'))
(Path.home()/'.config/systemd/user/ledger-mt5-bridge.service').write_text(service)
PY
systemd-analyze --user verify "$HOME/.config/systemd/user/ledger-mt5-bridge.service"
systemctl --user daemon-reload
# Run from the logged-in KDE desktop session; import only variables present there.
for name in DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS; do
  if [[ -v $name ]]; then systemctl --user import-environment "$name"; fi
done
# Ensure the correct demo terminal is open/logged in. No automated login command.
systemctl --user start ledger-mt5-bridge.service
systemctl --user status ledger-mt5-bridge.service --no-pager
journalctl --user -u ledger-mt5-bridge.service -n 30 --no-pager
ss -ltnp '( sport = :18765 )'
```

The last command must show **127.0.0.1:18765 only**, never 0.0.0.0, [::], a LAN
address or Meshnet address. Do not enable the service at login until acceptance
passes. `sudo loginctl enable-linger` is not required or recommended here: Wine
depends on the existing graphical session/terminal. No new trading process is
installed. If Wine fails under the resource limits, inspect its local journal;
do not remove loopback/authentication/identity checks to make it work.

## First Ledger acceptance: DEMO only, temporary database

Use Ledger's **native Linux** backend Python (the existing venv path below):

```bash
cd "$REPO/backend"
.venv/bin/python tools/check_mt5_bridge.py \
  --bridge-url http://127.0.0.1:18765 \
  --token-file "$HOME/.config/ledger-mt5-bridge/token" \
  --symbol XAUUSDs --confirm-demo
```

This verifies account environment before sync, uses real bridge calls and the
existing Ledger Journal importer in a new temporary database, repeats sync and
reports opaque account identity/counts/raw tick diagnostics. It never touches the
existing database or places orders. Repeat sync must create zero duplicates;
new broker activity during acceptance may require repeating a stable test.
An empty real history can prove connectivity but does not prove closed-trade
reconstruction. Retain the printed non-secret report for acceptance review.

Also verify: stop the service and repeat the checker (safe failure); restart it
and rerun (stable identity/idempotency). A LIVE profile must be rejected by the
client even though the terminal is demo. No automated login switching is needed.
Check the port from another device: connection to Fedora's LAN/Meshnet address
on 18765 must fail. This is required acceptance, not something Windows tests prove.

## Connect the existing Ledger instance after acceptance

Preserve a database backup before any ordinary backend upgrade/startup migration.
Use the existing deployment backup procedure; do not copy an actively writing
SQLite file with cp. The bridge itself requires **no schema migration**.
Add to the backend's private environment using the real Linux token path:

```dotenv
MT5_ENABLED=true
MT5_ENVIRONMENT=demo
MT5_BRIDGE_URL=http://127.0.0.1:18765
MT5_BRIDGE_TOKEN_FILE=/home/YOUR_USER/.config/ledger-mt5-bridge/token
MT5_LOGIN=
MT5_PASSWORD=
MT5_SERVER=
MT5_TERMINAL_PATH=
```

Do not put token content in .env, Git, frontend settings or Nginx. For extra broker
profiles, place bridge_url and bridge_token_file in that DEMO profile's backend
credentials configuration; do not silently repoint a LIVE profile. Keep other
profiles unchanged. Restart Ledger using its existing service procedure, then
Settings → MT5 DEMO → Test connection → select the verified account → Sync now.
Repeat sync; inspect closed trades and existing notes/IDs. Symbol discovery and
account snapshots are available; market history explicitly fails until UTC is
verified. Once accepted, optional login startup is:

```bash
systemctl --user enable ledger-mt5-bridge.service
```

The backend must run as the same desktop user or have a deliberately scoped ACL
for the token. Do not make the token world-readable to resolve a permission error.

## Automated verification for this checkpoint

- 412 MT5/bridge/broker-connection tests passed, including 24 bridge cases.
- 144 frontend tests passed; production build passed on unchanged retry after the
  existing intermittent Windows import resolver failure; chunk-size warning remains.
- git diff --check passed. No production database, terminal or account was changed.
- The preceding broader checkpoint passed 1,932 backend tests / 41 skipped and 31
  real Docker tests; that full run predates this bridge. It is not presented as a
  full run of the bridge tree.
- Fedora systemd/Wine behaviour, host loopback exposure and real Ledger DEMO
  discovery/Journal sync remain pending the user's acceptance run. No automated
  execution is enabled, and no order-based acceptance is authorized.

Rollback: disable/stop this service and clear MT5_BRIDGE_URL for Windows-native
access, or disable the MT5 profile on Linux. Never delete Journal records or the
Wine prefix. To inspect the port without authenticating, use ss; a GET request is
intentionally not a health/data endpoint. The authenticated checker is the health
and identity check.

## Advancing-clock evidence (24 October follow-up)

The checker now collects five tick diagnostics one second apart and returns
`clock_samples` and `clock_summary` alongside the existing `tick_diagnostics`.
Run the same documented command while Gold is trading. It can identify a current
0/+2/+3-hour candidate only with bounded receipt times and advancing quotes.
Stationary, ambiguous or wide-interval samples remain unverified. This does not
establish a seasonal rule, convert historical bars or enable execution.

The supplied raw timestamp 1792866678196 and receipt 1792855880555 differ by
10,797.641 seconds: consistent with UTC+3 and a 2.359-second-old quote. One
sample is insufficient to verify clock progression or DST. T01 continues to
require independently verified timestamp semantics. The user has now authorized
future demo acceptance trades, but no orders were sent and safety gates remain.
