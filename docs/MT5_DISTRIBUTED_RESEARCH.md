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
For 2026-10-16 14:00–14:05 UTC: 5 completed 1m NASUSD bars and 3,920 ticks,
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
  default 60 seconds (1–3600 configurable). Null before full observed warmup or
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

Stages 7–8: Runs now exposes a selection toolbar with Open/Use settings for one
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

9. Measured 2k–3.5k-trade performance acceptance and necessary fixes.
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

