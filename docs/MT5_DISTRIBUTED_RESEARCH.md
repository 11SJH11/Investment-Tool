# MT5 distributed research phase â€” 18 October 2026

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
Stage 2 now exposes explicit terminal symbol refresh and cached, searchable,
paginated metadata in Settings -> MT5 broker instruments. Select a verified account
first. Catalogs use the existing atomic app-settings store, scoped by opaque
provider/environment/server/account identity; no schema migration is required.
Raw broker names are preserved, calculation-mode classification is conservative,
and no discovered symbol becomes a verified CME instrument automatically.
Python symbol info does not expose weekly trading schedules: these remain unknown.
Failed discovery/account switches preserve the previous catalog. No automatic
terminal discovery happens on page load. Native errors are sanitized.

Stage 1 commit: `2fa2112`.
Verification after Stage 2: 51 focused backend tests passed (including 8 catalog
tests and 2 isolation tests); all 136 frontend utility tests passed; production
build passed (existing large-bundle advisory). Mocked catalog browser smoke passed
at 1024/1440/1920px with no page overflow or runtime errors. Actual terminal/provider
acceptance has not run; no isolated credentials or terminal have been configured.

Stage 2 commit: `9763ab1`.

## Broker-native history foundation (Stage 3)

Settings -> MT5 broker instruments -> Metadata -> Historical data exposes explicit
UTC window downloads and observed coverage. Bars support 1m/5m/15m/30m/1h/4h/1d;
ticks preserve bid/ask/last, flags and separate provider volume fields. Zero last
prices are unavailable. Equal millisecond ticks remain separate events. Bars must
be completed before the requested end; conflicting duplicate bars fail closed.
Neither the generic hub nor catalog changes NQ futures routing/accounting.

History uses content-addressed Parquet under the isolated data directory, publishing
the account-scoped manifest to app_settings only after validated atomic writes.
No schema migration. SHA256 integrity is checked on cache hits. Provider errors
or changed accounts publish no coverage. Exact repeated requests reuse local data.
Observed first/last timestamps and per-field non-null/positive counts do NOT imply
continuous coverage or exchange-volume availability. Weekly sessions and DOM remain
unverified. Current symbol metadata is explicitly not historical contract metadata.

Bounds: 366 days of bars / one day of ticks per request; native chunks are seven
days / one hour respectively, with a total 500,000-row ceiling. Oversized history
must be requested in smaller windows. Cached snapshots currently reuse exact
requests, not arbitrary overlapping-window queries. These datasets are not yet
wired into normal Backtest selection or Research Agent dataset approval (later stages).
The Python API is synchronous: cancelling a browser request does not interrupt a
native history call. No background download queue or fabricated gap filling.

Verification after Stage 3: 68 focused backend tests passed (17 history-hub tests);
136 frontend utility tests passed before the history UI addition; production build
passed after it. Mocked catalog/coverage browser smoke passed at 1024/1440/1920px
without overflow/runtime errors. Full-suite and real-provider acceptance are pending.

Stage 3 commit: `a668f63`.

## Real terminal acceptance

Read-only acceptance against the already-running local demo terminal succeeded
without reading the stable checkout's credentials or changing account/login:
344 symbols discovered (238 CFD, 106 forex); NASUSD is a broker CFD.
For 2026-10-16 14:00â€“14:05 UTC: 5 completed 1m NASUSD bars and 3,920 ticks,
with cached Parquet SHA256 verification passing. All 3,920 ticks supplied bid/ask;
none supplied a positive last price or positive last-trade volume. The five bars
had positive tick volume but all-zero real volume. No exchange-volume availability
claim is made. No order APIs were called. Acceptance artifacts are ignored under
`.ledger-runtime/acceptance`, separate from both applications' runtime databases.
This five-minute sample proves retrieval, not multi-year coverage or execution parity.
Use a separate MT5 terminal installation/data folder if concurrently testing different
accounts; native terminal account state is shared across connected processes.

## Causal microstructure foundation (Stage 4)

The existing Market Concepts registry now supports explicit tick inputs, without
passing them through OHLCV calculations or changing the bar engine. Added:

- `spread.current.v1`: ask minus bid, price units; missing/crossed quotes -> null.
- `spread.mean_window.v1`: arithmetic quote-weighted mean over `(t-window,t]`;
  default 60 seconds (1â€“3600 configurable). Null before full observed warmup or
  if any quote in the window is invalid. This is not a time-weighted spread.
- `tick_activity.count.v1`: observed event count over the same window, not exchange
  trades/volume. Equal-timestamp events retain provider ordering.

Observations preserve occurred_at, confirmed_at and available_at. Delayed observations
are withheld until available. Historical inputs without measured availability use
event time explicitly; they do not claim measured live latency. Existing bar observations
default availability to confirmation. Tick inputs cannot silently feed bar concepts.
Dataset/source fingerprints use the existing registry. Prefix mutation, missing quote,
delayed availability and same-timestamp fixtures pass. No DOM, speculative imbalance,
fill simulation or strategy trading-rule changes were added.

The framework is implemented; attaching these summaries to approved research datasets,
canonical results and packs remains part of the following stages. No MT5-derived
strategy is yet enabled for backtest or distributed execution.

Checkpoint verification: 8 microstructure tests plus 7 existing Market Concepts
tests and the configuration-template test passed (16 total). Real NASUSD quote data
also passed full-input versus truncated-prefix equality for all three concepts
(1,691 observations visible at 14:02 UTC). The first full run finished with 1,485
passed, 45 skipped and one configuration-template failure: the newly introduced
CORS alias was missing from .env.example. That omission is fixed and its focused
test passes. A clean final full run remains required; do not report this run as green.

## Remaining staged work

Stage 4 commit: `4a0ce2f`.

Stage 5 now adds `ledger.experiment.v1` metadata to the existing Ledger result
shape. New Python runs record the core executor SHA (engine/context/models),
configuration hash, strategy/data provenance, lineage, role, effective execution
and cost settings, and RECORDED/UNAVAILABLE section availability. Parent research
workers finalize lineage without replacing the worker's execution identity.
Workspace persistence uses the same contract; it remains hidden in normal UI.
The existing result store validates contract/configuration agreement. Historical
snapshots are not rewritten or assigned current code identity. Run Viewer and the
reproducibility export expose the recorded contract. Missing MT5 evidence is never
computed as zero by normalization. MT5 fixture normalization is tested; this is
not an implemented tester or parity certification.

Stage 5 validation: 63 tests passed across contract, parent research, reproducibility,
source archives and Workspace; production build passed. No database migration.

Stage 5 commit: `3c0e3d6`.

Stage 6 implements the `ledger.research_pack.v1` schema and deterministic
`ledger.research_bundle.v1` ZIP manifest. Run Viewer -> Download offers bundle,
pack JSON, trades CSV, summary JSON, analysis JSON/CSV, configuration/provenance,
and the full saved result. The existing visual PDF Trade Review pack remains.
Bundles contain JSON schema, file sizes and SHA256 hashes; fixed ZIP timestamps
make repeated exports deterministic. Missing trades do not become zero-trade
research conclusions. Raw market history is not embedded. CSV text is protected
against formula interpretation. Exports have a 100 MiB uncompressed budget.
Research analysis reuses the existing Research Agent calculation, not an alternate
metrics engine. Only recorded microstructure is exported; automatic attachment of
new tick evidence to runs remains future integration work.

Stage 6 checks: 15 focused export/contract/reproducibility tests passed, all 136
frontend tests passed, production build passed. Mocked Run Viewer provenance and
binary bundle-download smoke passed at 1024/1440/1920 without overflow or runtime
errors. No migrations or original-checkout changes.

Stage 6 commit: `1501091`.

Stages 7â€“8: Runs now exposes a selection toolbar with Open/Use settings for one
run, explicit Compare selected for multiple runs, Download selected, atomic Delete
selected, and Clear selection. Comparison reuses RunComparison; merely selecting
rows no longer triggers heavyweight comparison loading. Downloads contain separate
run folders and a checksummed comparison-evidence document; no automatic winner,
parent relationship or aggregate portfolio return is inferred. Maximum 30 runs,
100 MiB uncompressed. Existing visual/PDF workflows are preserved.

Deletion checks all selected IDs in one SQLite transaction before removing any.
Research ownership, campaign/action references and parent-experiment references
block the whole deletion with a visible reason. No data migration is required.
Focused checks: 34 export/retention/parent-research tests; browser single/bulk
downloads, explicit comparison, protected-delete error and selection reset passed
at 1024/1440/1920. All 136 frontend utility tests and production build passed.

The broader regression run exposed a stale synthetic decision fixture which copied
a real run's canonical contract then changed configuration/trades. Production hash
validation remains strict; the fixture now identifies its synthetic executor and
configuration explicitly. All 6 decision tests and 9 cost tests pass independently.
Final full-tree regression remains pending until the verification record below.

9. Measured 2kâ€“3.5k-trade performance acceptance and necessary fixes.
10. ExperimentExecutor integration.
11. Real exact Python/MQL5 parity proof.
12. Tester execution and automatic result ingestion.
13. Independent local tester agents.
14. Remote/cloud feasibility only after parity.
15. Bounded multi-family research/governance.
16. Official Robinhood interactive OAuth/MCP, subject to registration prerequisites.
17. Final whole-phase regression and end-to-end acceptance.

MT5 distribution must remain disabled until actual
Ledger/MQL5 decision/state parity is demonstrated, not merely fixture P&L similarity.

Official references: [MT5 symbols](https://www.mql5.com/en/docs/python_metatrader5/mt5symbolsget_py),
[MT5 ticks/UTC](https://www.mql5.com/en/docs/python_metatrader5/mt5copyticksrange_py),
[Robinhood external agents](https://robinhood.com/us/en/support/articles/onboarding-an-external-agent/).
Robinhood registration/auth prerequisites still require investigation; no unofficial
API or token extraction fallback is authorized.

## Current holdings correction
Portfolio positions now exclude inactive snapshots before pagination/counting. History, notes and tags remain stored; failed sync status exposes potentially stale last-verified holdings. Verified with 42 broker/Portfolio tests, 136 frontend tests and production build. Prior checkpoint provenance/export verification: 19 tests passed; the previous full run's three stale-fixture failures are corrected. Full final-tree suite remains due after Gold work.


## Gold acceptance and updated priority order (2026-10-18)

The updated brief prioritises genuine Gold research, then controlled MT5 execution,
then responsive workflows, then advanced distributed research. Existing stages 1–8
are preserved; `43327dd` contains the verified bulk-export/selection checkpoint and
`099269b` the current-holdings correction.

The Gold source is copied byte-for-byte from original checkout commit `f96d62a`,
not merged with research outputs or credentials:
`backend/app/backtesting/strategies/gold_asia_15m_ifvg_research_v1.py`.
SHA-256: `236611d915d771f9b9a6558c5a57941ae0985b53664c13153908819e795d6e14`.
No frozen signal, stop, target or breakeven rule was edited.

New automatic entry-day defaults are Monday–Friday for equities and Sunday–Friday
for known spot Gold/futures session profiles. All seven weekdays are selectable.
Explicit saved weekday settings remain explicit. API requests that omit weekdays
resolve and save their effective days. Sandbox engine configuration uses the same
resolution. These filters do not assert broker opening times or holiday coverage;
provider historical bars remain authoritative and no missing candles are created.

Selecting Gold IFVG now selects XAUUSD, 1m execution, automatic market session and
its declared completed 15m input. Its Asia session is labelled by the local New
York **start date**, including Sunday evening; midnight is outside that session.

Sizing calculations are unchanged. Trade metadata now records target monetary risk,
actual initial risk and percentage, initial notional exposure, exposure cap and a
sizing limitation flag. Trade Review exposes target risk, notional and limitation;
existing metadata exports carry these fields. Zero-cost runs are visibly labelled
frictionless. The interface explicitly distinguishes metal units from MT5 lots and
does not invent broker leverage, margin or costs.

Synthetic acceptance uses entry 3001, short stop 3010, target 2992. With $10,000,
1% target risk and 1x leverage, quantity is 10000/3001 metal units, actual risk is
9*10000/3001 (about $29.99), and notional is $10,000. Outcomes assert exactly +1R,
-1R, or 0R after +0.68R triggers next-minute breakeven. January, spring DST and
fall DST Sunday fixtures all pass, along with exclusion of incomplete 15m signals.
These are mechanical acceptance fixtures, not evidence of a profitable edge.

Read-only real MT5 acceptance found the exact broker Gold symbol **XAUUSDs**, not
XAUUSD. Current terminal metadata: Gold spot, XAU/USD, 100 ounces per lot, 0.01
price tick, $1 tick value per lot, 0.01 minimum/step lots. `margin_initial=0` is not
interpreted as free margin or permission to infer leverage. A 2026-10-16 14:00–14:05
UTC request retrieved 5 completed minute bars and 1,873 bid/ask ticks. Both Parquet
fingerprints verified on cache read. Real trade volume is unavailable. No orders
were sent. MT5's calculation-mode classification is retained separately from the
instrument's Gold identity.

Still required before claiming full Gold research acceptance:
- Automatic provider selection and verified broker-symbol mapping into backtests.
- OANDA versus MT5 comparison: this isolated worktree has no configured OANDA
  credentials; the original checkout's environment was not read or copied.
- Broker lot/margin execution model and historical session/holiday validation.
- Research Agent's US-equity-only preparation/discovery and forced regular session
  need correction; required 15m history must share protected dataset boundaries
  and provider bindings with 1m execution. Do not simply bypass the firewall.
- Genuine Gold campaign with saved baseline/numeric/Critic/Manager evidence.
- Demo execution, live authorization gates and the remaining roadmap above.

Browser acceptance: Gold settings and Portfolio current/stale holdings passed at
1024, 1440 and 1920 pixels without page overflow or runtime errors. All 137 frontend
unit tests pass; production build passes (existing ~999 KB bundle warning).
Focused backend acceptance: 42 Gold/engine/provenance/decision tests and 42
broker/Portfolio tests pass. Full backend result is recorded below when complete.

A measured saved-run smoke also passed using the existing isolated benchmark:
3,000 trades, 660,000 equity points, real repository section endpoints and mocked
run-list discovery. Headline 534 ms; first performance-chart paint 4,100 ms;
Analysis paint 469 ms. Backend performance projection was 3,383 ms and returned
1,017,334 bytes. Scroll max frame gap 16.6 ms, zero frames above 32 ms; no page
overflow at 390/1024/1440/1920 and no runtime errors. This cold observation ran
alongside backend tests, so it is not an isolated before/after speed claim. It
identifies performance-series preparation as remaining work; Stage 9 is not marked
complete. Raw reports stay in ignored `.ledger-runtime/heavy-run-performance.json`
and `.ledger-runtime/heavy-benchmark/measurements.json`.

Final checkpoint verification (2026-10-18): **1,522 backend tests passed, 45 skipped**
in 511.04 seconds; one existing Starlette/httpx deprecation warning. Skips cover
opt-in Docker acceptance and optional local strategies; no Docker acceptance is
claimed for this run. **137 frontend tests passed**, production build passed,
`git diff --check` passed. The original checkout remained untouched and clean for
tracked files. No DB schema migration was introduced by the holdings/Gold fixes.

## Gold campaign preparation checkpoint (2026-10-18)

The preceding limitation about equity-only campaign preparation is now addressed:
- Spot-metal cached discovery and provider preparation are supported alongside
  equities. Futures remain explicitly blocked pending correct session/provenance
  integration, rather than being treated as stocks.
- Campaign UI submits `session=auto`. Backend rejects equity-session filters for
  spot-metal campaigns, while preserving explicit valid session choices.
- Required strategy/concept timeframes are planned automatically. Gold IFVG needs
  1m and 15m, but remains one primary-timeframe project. The existing engine's
  optional ORB daily-diagnostic behaviour is preserved.
- Every required input must cover the primary session dates and use the same
  provider namespace. Missing history fails preparation; dates are not shortened
  or shifted to hide gaps. This is observed-date coverage, not certification that
  every intraday candle is present.
- Input timestamp fingerprints and provider namespaces are part of the hashed
  plan. Project bindings include both 1m and 15m. Existing dataset boundaries and
  holdout guards apply to both; no extra holdout authority was added.
- Preparation failures now carry safe, actionable categories/messages. Raw provider
  exception text remains excluded. The frontend displays the safe explanation.

Validation: **92 focused backend tests passed** across Gold campaign acceptance,
cached discovery, provider preparation, launch, project provisioning and campaign
control. The ten new Gold cases include a complete job-queue campaign using the
real BacktestEngine and synthetic cached multi-session data: two saved development
trades (+1R, -1R), Sunday execution enabled, untouched holdout, no model or Docker
required. Separate tests verify missing 15m input, provider changes, holdout access,
DST date labels, both prepared input jobs, and safe failure messages.
**138 frontend tests passed**, production build passed, and diff checks passed.
The latest whole-backend run remains the prior checkpoint's 1,522 passed/45 skipped;
it is not presented as a full-suite run of this newer checkpoint.

No schema migration: additional dependency provenance and failure detail live in
existing versioned campaign/project JSON. Original checkout and credentials remain
untouched. A genuine provider-backed Gold campaign with numeric research and
Critic/Manager evidence is still required before full Priority A acceptance.
Automatic provider selection, broker lot/margin integration, MT5 demo execution,
performance/preview work and the advanced roadmap remain outstanding.


## Gold provider routing and real baseline (verified 19 October 2026)

Automatic Gold history routing now supports the intraday research path. Configured
OANDA remains preferred. Otherwise Ledger requires exactly one verified XAU/USD
spot symbol from selected MT5 accounts, with bid-chart metadata and positive
contract/tick/lot specifications. Ambiguous or incomplete catalogs fail explicitly.
Selection is pinned: provider failures do not switch sources. This is eligibility
routing, not yet an empirical ranking of provider quality or coverage.

MT5 datasets use separate account/environment/specification-derived namespaces.
History reuses the read-only hub, bounded seven-day requests and verified Parquet
hashes. Canonical caches retain broker symbol, bid-price basis, tick-count volume,
real volume and spread fields. Saved results record source details and namespace;
Run Viewer exposes provider/feed/broker symbol. Warnings distinguish bid candles
from OANDA midpoint candles and tick counts from exchange volume. Daily bars and
live quotes are unsupported by this adapter until their semantics are established.

Real-terminal acceptance saved an isolated Gold IFVG baseline for Sunday
11 October 2026: XAUUSD mapped to XAUUSDs, 175 minute bars and 12 fifteen-minute
bars, one trade, zero rejected signals. The short entered at 4190.63 at
2026-10-12 03:00 UTC and stopped at 4199.48 at 03:10, returning -1R. Quantity
was 2.386276049185922 metal units; actual initial risk was $21.11854303529411
versus the $100 target because of the 1x exposure cap. This is frictionless
bid-bar research, not broker-lot execution parity. No orders were sent. Observed
minute history starts at 21:05 New York: complete coverage from the strategy's
20:00 session start is NOT certified. The local, ignored acceptance report is
`.ledger-runtime/gold-acceptance/sunday-baseline.json`.

Final verification against this code tree:
- Full backend: 1,545 passed, 45 skipped, one existing deprecation warning,
  587.35 seconds. Skips include opt-in real Docker tests and optional strategies;
  no fresh Docker acceptance is claimed.
- Focused routing/history/catalog/services/Gold campaign tests: 50 passed.
- Frontend: 138 passed, zero failed/skipped.
- Production build: passed; existing bundle-size advisory remains.
- Mocked Gold settings and Portfolio holdings/stale-state browser checks passed
  at 1024, 1440 and 1920px without runtime errors or page overflow.

No schema migration: existing result JSON and optional Parquet columns carry the
new evidence. The original checkout and its credentials remain untouched.

Remaining Priority A work: OANDA/MT5 quality comparison (isolated OANDA credentials
are unavailable), complete historical-session validation, broker lot/margin and
bid/ask execution modeling, and a genuine multi-session Gold research campaign
with numeric/Critic/Manager evidence. Terminal history is limited by the connected
broker/terminal; missing history is not fabricated. MT5-only routing requires a
configured profile at backend startup. Controlled demo/live execution and the
remaining broader roadmap are not complete.


Campaign feasibility follow-up (19 October): the 20 July to 17 October 2026
request retrieved 88,931 minute bars and 5,971 fifteen-minute bars across 78
observed New York dates. The unchanged default dataset policy (250 warmup,
252 development, 63 holdout dates) rejected this history as insufficient.
A separate 21-28 October 2024 probe failed for 1m with BrokerHistoryError but
returned 460 requested 15m bars. The market-cache service also filled intervening
15m history, yielding 622 observed cached dates at that timeframe. Older 15m
availability does not satisfy the required 1m execution input. This establishes
an unresolved minute-history availability issue, not its cause or an exact broker
retention limit. No policy thresholds were reduced and no campaign was falsely
marked complete. Probes inspected timestamps/counts, not holdout performance.
Local reports: `.ledger-runtime/gold-acceptance/campaign-feasibility.json` and
`campaign-older-history-probe.json` in the same directory. A longer verified 1m
source and enabled/authorized model service remain necessary for full campaign
acceptance. These read-only probes introduced no application or schema changes.


## Priority B foundation: read-only broker sizing (19 October 2026)

Settings -> MT5 broker instruments -> Metadata now includes a collapsed Broker
sizing estimate. Enter broker prices and monetary target risk to calculate current
account-currency stop loss, broker lots and margin. The backend also accepts an
exclusive equity-percent risk input. Broker quantity is rounded down to volume
step and capped at volume maximum; minimum-lot risk, actual rounded risk and free
margin failures are explicit. Entry/stop must align with tick size. The resulting
size is recalculated through the native broker function before presentation.

The API is POST /brokers/{profile_id}/sizing-preview. It uses the existing profile
and process-global terminal locks, selected account/environment verification and
sanitized errors. No order_send or order_check call exists in this implementation.
Execution remains disabled for demo AND live. This estimate is not an approval or
an executable order: costs, gap/slippage risk, stop-distance rules, aggregate
exposure, daily loss and pending-order risk require the future execution gateway.
MT5 margin estimates exclude existing positions/pending orders; the UI says so.
No historical backtest sizing or strategy rules were changed. No migration.

Official calculation contracts:
- https://www.mql5.com/en/docs/python_metatrader5/mt5ordercalcprofit_py
- https://www.mql5.com/en/docs/python_metatrader5/mt5ordercalcmargin_py

Real demo-terminal calculation for XAUUSDs, hypothetical buy 4200 / stop 4190 /
$100 target: 0.10 broker lots, $100 estimated stop loss, $420 estimated margin.
No orders sent. Local ignored report: .ledger-runtime/gold-acceptance/sizing-preview.json.

Verification: 69 focused backend tests passed, including 19 new sizing cases;
138 frontend tests passed, production build passed, git diff --check passed.
Mocked browser acceptance exercised explicit calculation and the request/result
contract at 1024/1440/1920px, with no overflow/runtime errors. Backend cases cover
long/short, equity-percent sizing, volume rounding/max/min, margin failure,
account changes, disabled profiles, safe native failures, non-linear recalculation,
API validation and read-only live estimates. The previous whole-suite result of
1,545 passed/45 skipped predates this sizing checkpoint; it is not a whole-suite
claim for this newer tree.

Next Priority B steps: durable per-account/strategy authorization and risk policy,
order intent/idempotency journal, demo-only submission with broker checks,
reconnect/reconciliation, and only then separately authorized live capability.
Priority A campaign/data limitations above remain unresolved; later preview,
Replay, performance and distributed research work remains pending.
