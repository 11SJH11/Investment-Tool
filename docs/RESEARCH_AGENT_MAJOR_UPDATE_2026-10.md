# Ledger Research Agent major update — October 2026

## Boundary and evidence

Boundary: **`afb73e9f4b0679fd5a7c8b10498289b7a8fd610b`**, committed
2026-10-05, “Keep trade review autoscaling local to visible price action”.
This is the latest committed handoff boundary in this working tree. The previous
Research Agent foundation handoff accumulated subsequent uncommitted checkpoints;
it was not another committed release. This document consolidates those changes
and the Docker continuation. It does not attribute pre-existing user strategy
files to the Docker implementation. The file inventory below is derived from
`git diff HEAD` and untracked application/test/document files.

## Executive summary

Ledger now supports a bounded development-research workflow around immutable
backtests: dataset registration, baseline freezing, deterministic diagnostics,
optional three-role LLM review, preregistered numeric experiments, budgeted trials,
candidate robustness, explicit validation and human research decisions. Market
Concepts provide independently versioned causal observations rather than trading
rules. Source archives and manifests improve auditability without pretending to
archive complete historical market data.

Generated source remains quarantined outside strategy discovery. Explicitly
approved development checks execute that Python only inside short-lived Docker
containers. The existing trusted engine remains outside the container and owns
fills, costs, account arithmetic and results. Containers return bounded JSON
signals, not trusted performance reports or job instructions.

This is a local research application, not a public multi-tenant code-execution
service, broker execution system or automatic strategy promotion mechanism.

## Architecture and ownership

| Layer | Responsibility |
| --- | --- |
| Research repository | Projects, datasets, lineage, inspection debt and audit events |
| Researcher / Devil / Manager | Optional bounded structured-text review; no tools or trading authority |
| Deterministic services | Diagnostics, hypotheses, experiment cells, budget reservations, comparisons and verdicts |
| Existing backtest queue | Trusted parameter experiments, baseline and validation execution |
| Frozen candidate services | Cost stress, declared regime pairs, single-rule simplification and validation grants |
| Quarantine and sandbox coordinator | Inert source, explicit approval, four checks, cancellation and durable evidence |
| Docker worker | Generated module import, interface validation, stateful strategy decisions on completed bars |
| Trusted BacktestEngine | Signals validated on ingress; engine alone owns fills/accounting/metrics |
| Frontend | Consent, monitoring, review and explicit actions; no backend schedule depends on browser polling |

No second strategy registry is introduced in Ledger. The image has a local
no-op registration decorator for compatibility; it cannot register anything in
the host. Existing direct-file strategy refresh remains a **trusted local code**
workflow and is distinct from generated source quarantine.

## Roles, deterministic services and workflow

The optional committee makes sequential Researcher, Devil's Advocate and Manager
calls using strict structured outputs. It receives bounded verified development
summaries, declared strategy inputs and research limits. It has no execution tools,
broker credentials, journal notes, raw bars, raw source or holdout results. Its
recommendation does not approve a trial. Explicit preregistration freezes the
proposal before execution.

Deterministic diagnostics report sample counts, average/total R, winner retention,
lost large winners, MFE/MAE availability, time/direction/year/month breakdowns,
concentration and descriptive cost sensitivity. Missing metrics remain missing;
small samples are labelled. The existing engine is rerun for path-dependent
experiments; static filtering is not presented as equivalent to a rerun.

The development loop supports explicit authorization for 1–10 cycles:
review → preregister → approve bounded cells → wait → verified feedback.
It retains durable request identities, resumes from recorded state, and does not
repeat a completed experiment because a browser reconnects. Candidate freezing
stops the loop. The loop does not automatically generate Python, consume holdout,
promote strategies or make final acceptance decisions.

Candidate checks include fixed-cost stress scenarios, declared independent regime
windows and single-parameter simplification. Each starts with unchanged control
parity. Regime baseline/candidate pairs share a fingerprint; independent windows
are not stitched into fictitious portfolio returns. Declaration-only ablation
suggestions require the user to verify off semantics. Manager guidance recommends
the next missing check, waits for active work and respects remaining budget; it
does not rank profitability or issue approvals.

Validation requires an explicit candidate-bound dataset grant and fixed criteria.
Default criteria require at least 30 trades, average R >= 0 and R profit factor
>= 1. Unavailable profit factor is insufficient evidence. Inspection permanently
consumes the dataset's unseen status even when a later run fails. Final decisions
are immutable `REJECTED` or `ACCEPTED_FOR_RESEARCH`, with structured human review
and reverified passing validation required for acceptance. Neither authorizes
deployment or orders.

## Dataset firewall, lineage and anti-overfit controls

Development coverage must include all requested warmup. Locked holdout and future
OOS overlap is blocked before loading saved result JSON and at provider/cache data
access, across projects and futures aliases in the same contract family. Provider
namespace bindings prevent silent feed changes. This firewall protects application
research paths; it cannot reconstruct historical human exposure or prevent trusted
manual Python from reading other data.

Lineage records baseline run IDs, source identities, hypotheses, immutable candidate
snapshots and child source hashes. Generated drafts additionally bind the exact
parent candidate hash. Editing a source does not recalculate historical results.
Changes require a new draft/experiment, not replacing an observed experiment.

Research debt counts inspections and experiment use; it is not a calibrated
probability of overfitting. Hypothesis definitions, failure criteria and numeric
cells are preregistered. All tested outcomes, including failures and removed
winners, remain evidence. No automatic “best strategy” declaration is made.

Default project limits are 80 simulation reservations, 60 minutes per ordinary
trial, 12 LLM calls, 12 hypotheses, 9 variants per hypothesis and 60 total variants.
The generated-code route additionally limits each approval to four simulation
reservations, a single symbol, 10,000 total supplied bars and a 10–600 second
requested deadline (120 seconds in the UI). Each project permits at most ten
immutable code drafts. Failures do not refund simulation reservations.

## Market Concepts

Optional `StrategySpec.concepts` declarations expose `ctx.concept(alias)` using
the same completed-bar boundary as ordinary indicators. Concepts emit typed series,
points, events, zones and states with occurrence and confirmation times. Exact
version keys, normalized parameters, dependency graphs, implementation hashes,
input fingerprints and bounded caches make their interpretation explicit.

| Initial experimental key | Definition and caveat |
| --- | --- |
| `session_vwap.new_york.v1` | Canonical HLC3/volume VWAP reset by New York calendar date; not CME evening-session VWAP |
| `swing.strict.v1` | Unique high/low with default 2 left and 2 right completed bars; ties rejected; confirmation delayed until right bars complete |
| `structure.strict.v1` | Higher/lower/equal same-side confirmed strict 2/2 pivots; not an entry rule or BOS model |
| `fvg.three_candle.v1` | Three-candle gap confirmed at third close; no mitigation or displacement lifecycle |

No frozen Gold, Momentum, ORB or VWAP strategy was migrated to these definitions.
Matched-input tests establish specific VWAP/pivot compatibility only; differing
session, tie and eligibility rules are not asserted equivalent. New semantics
require new versions. Concept audits use explicit development consent, at most
2,000 prepared bars, finite prefix probes and confirmation-aware visual samples.
Post-confirmation follow-up is labelled research-only. Benchmarks are descriptive,
not evidence of a profitable edge or universal performance SLA.

## Storage and migrations

All Research Agent tables are additive `CREATE TABLE IF NOT EXISTS`, initialized
by their services rather than destructive schema replacements:

- `agent_projects`, `agent_datasets`, `agent_events`;
- `agent_hypotheses`, `agent_reviews`, `agent_loops`, `agent_trials`;
- `agent_candidates`, `agent_validations`, `agent_decisions`;
- `agent_concept_audits`, `agent_code_drafts`;
- **`agent_sandbox_runs`**: ID, project ID, unique draft ID and durable JSON document;
- `strategy_source_blobs` and `strategy_source_archives`: content-addressed bytes
  and manifests, deduplicated and verified on export.

The broader post-boundary integration also advances schema version to 18 and
adds Journal `is_automated`, `execution_source`, `strategy_id`, `strategy_name`
and `strategy_run_id`. Manual/replay/backtest/import origins are migrated using
known facts; unknown imported automation remains unknown. Existing IDs, notes,
attachments, reviews and broker reconciliation identities are preserved.

Research-owned saved runs are protected from ordinary deletion, including archived
project evidence. The Docker step does not rewrite existing runs. Its result and
resource/provenance record live in the single durable sandbox-attempt document;
repeated approval returns that same record. Recovery never inserts duplicate
performance evidence or automatically retries an interrupted attempt.

## Generated strategy lifecycle

1. Store a uniquely named `research_child_...` draft against a frozen candidate.
   AST parsing is advisory only. Raw source stays in SQLite, outside discovery.
2. Explicitly approve control parameters (feature disabled), candidate parameters
   and a deadline. The request becomes immutable and consumes four reservations.
3. Require Linux/amd64 Docker, cgroups v2, seccomp and a matching prebuilt image.
   Image absence, stale bundle, daemon failure or failed cleanup blocks execution.
4. Revalidate frozen parent/source/data and prepare only permitted development data.
5. Rerun the trusted parent and compare its saved result digest.
6. Import/validate generated code **inside Docker** and run feature-off control.
   Exact trades, metrics and equity parity are required. Failure records the first
   divergent path/value and prevents candidate performance evaluation.
7. Run the candidate, then a fresh-container primary-prefix replay. Compare every
   returned prefix signal. Only a passing run receives completed evidence.
8. Remove containers, record the terminal state and retain development evidence.
   Drafts remain quarantined; success is not normal registry activation.

States are `QUEUED`, `RUNNING`, then `COMPLETED`, `FAILED`, `CANCELLED` or
`INTERRUPTED`. Phase, safe failure category, parity, prefix evidence, resource
samples and provenance are visible in the candidate's sandbox section. Browser
navigation does not own execution. Parent decisions wait for active sandbox work.

## Docker isolation and threat model

Generated Python is arbitrary and untrusted. AST checks are not a security
boundary. No generated Python is executed, imported or unpickled in the backend.
The boundary is Docker plus a narrow validated JSON signal protocol. Even a
compromised worker cannot supply trusted account results, DB mutations, arbitrary
jobs, a registry update or a broker call through that protocol.

The image build stages an explicit allowlist into a private temporary directory:
strategy base/models/context, canonical indicators, Market Concepts and the worker
protocol. No repository-root copy, settings, `.env`, databases, provider/broker
services or other strategy modules enter the build context. Python base image
resolution is recorded by digest; execution is pinned to the resulting immutable
image ID. The bundle manifest is checked before each approval; edits require an
operator rebuild. Build-time package downloads are trusted setup operations,
separate from generated-code execution.

Runtime restrictions:

- Linux/amd64; non-root UID/GID **65532:65532**;
- **no host mounts**, Docker socket, host environment forwarding or credentials;
- `--network none`, no published ports, no host IPC, no privileged mode;
- read-only root; all capabilities dropped; `no-new-privileges`; Docker default seccomp;
- only `/scratch` writable for ordinary files: 32 MiB tmpfs, `noexec,nosuid,nodev`;
- `--ipc none` removes shared-memory scratch; standard kernel pseudo-devices remain;
- 512 MiB memory and equal memory+swap ceiling, one CPU, 64 PIDs, 128 open files,
  zero core-dump limit; no restart policy or Docker log accumulation;
- 8 MiB request and 64 KiB reply bounds; strict JSON nesting/numbers/keys/signals;
  stdout protocol flooding fails closed; stderr and non-protocol stdout are discarded.

Only completed raw OHLCV/availability and allowlisted futures provenance columns
are transmitted. Full engine frames, future rows, post-trade diagnostics and
undeclared future-session/derived columns are not available even through private
worker context attributes. Higher-timeframe `available_at` is honored. Indicators
and concepts calculate from those same completed snapshots. Existing position and
equity are copies; mutating them cannot change host account state.

Containers share the Docker host kernel; this is defense in depth, not a proof
against kernel vulnerabilities. Keep Docker patched. The host Docker daemon and
operator-built image are trusted. Default seccomp is not a bespoke syscall proof.
The local application must not be exposed publicly as an unauthenticated remote
code execution service. A malicious strategy can emit misleading legal signals
or use hard-coded information; finite parity/prefix checks cannot prove intent or
universal determinism. They do not grant trading authority.

## Independent crash recovery and cleanup

A trusted host guardian starts before the container starts executing code. It is
a separate Python `-I` process with a minimal environment and the exact immutable
container ID. It removes that container on deadline or EOF from its owning
backend. The OS delivers EOF if the backend dies, so the execution limit does
not depend solely on an in-process thread. The ordinary watchdog also handles
manual cancellation. Confirmed removal stops the guardian; concurrent cleanup
accepts only verified absence as success.

Containers carry `com.ledger.research.sandbox=<database-owner-hash>` and random
`ledger-research-...` names. Recovery enumerates only that label, never Docker-wide
prune. On restart, prior active records become `INTERRUPTED` after owned-container
cleanup; terminal records are retained. Missing/already-finished containers and
repeated cleanup are safe. A Docker outage produces cleanup failure and blocks
further sandbox approvals; ordinary non-sandbox Ledger remains available.

If the Docker daemon itself cannot be reached, no host process can honestly
guarantee immediate removal. Reconciliation retries when Docker returns. There
is no automatic host execution fallback. One Ledger backend per database is the
supported operating model; parallel server instances are not a distributed lease
system.

## Security/correctness acceptance matrix

| Requirement | Evidence |
| --- | --- |
| No internet / external DNS | Real IP and hostname connection attempts fail; external DNS lookup fails |
| No host secrets/repo/DB/socket | No mounts; credential variables and host/service paths absent; authority imports fail |
| No other-strategy mutation | Image files reject writes; each container has private scratch and processes |
| No host registry/jobs/orders | RPC accepts signals only; host registry and job count unchanged in E2E; broker/job services absent in image |
| No scratch escape | Root, image and `/dev/shm` writes fail; `/scratch` write succeeds |
| Process/memory/CPU/output bounds | Real fork-limit, oversized allocation, infinite loop, stdout flood and infinite stderr fixtures fail or terminate safely |
| Cancel / backend crash | Explicit cancellation, EOF and forcibly killed initialized coordinator remove containers |
| Orphan recovery | Owned orphan removal, already-finished/missing/repeated cleanup, unrelated-owner survival and restart terminal reconciliation |
| Invalid source / output | Syntax/import/interface/key failures inside Docker; strict JSON and signal validation on host |
| Control parity | Mock-model feature-off control matches parent; a changed stop records first divergence and blocks candidate |
| Causal evidence | Completed-only private frames, delayed HTF exclusion, stripped post-trade/future columns, confirmed swing test and fresh prefix replay |
| Immutable evidence | Parent snapshot unchanged, idempotent approval, budget consumption and no automatic recovery rerun |

## Reproducibility, manifests and resource evidence

Normal saved runs now capture loaded strategy source archives and execution
environment metadata. Explicit source export verifies blob and manifest hashes;
it never substitutes today's files for missing legacy source. Reproducibility
exports contain saved config/result/source/data/environment identities and clearly
list missing artifacts. They are not complete executable or historical-bar archives.

Sandbox evidence additionally records immutable image ID, generated source hash,
parent hash, configuration hash, full prepared-data fingerprint, signal-trace hash,
host implementation file hashes, host package environment, policy limits and
per-phase wall time. Docker CPU/memory/PID/IO values are terminal samples, **not
peak usage**; killed tasks may have no sample. Actual engine results are constructed
on the trusted host and hashed before persistence. Image content ID preserves
the exact built environment while that image is retained; the build recipe alone
is not a claim of byte-identical future rebuilds.

## Cost controls and external services

The committee is opt-in: `RESEARCH_LLM_ENABLED`, `RESEARCH_LLM_API_KEY`, explicit
`RESEARCH_LLM_MODEL`, output-token limit and configured input/output USD-per-million
prices. No default model or guessed free price is selected. Autonomous numeric
cycles require a positive project monetary budget. Reservations conservatively
allow 100,000 input tokens plus configured output allowance per call, without
cache discounts. Unknown pricing blocks budgeted calls. Recorded usage is an
estimate from supplied prices, not invoice reconciliation; unused reservation is
not silently recycled.

No live LLM, broker or market-provider call is needed for automated acceptance.
The tests use synthetic market data, isolated databases and mocked model output.
Real research still needs appropriate historical-data entitlement and, optionally,
explicit external-summary consent and a configured model. The container receives
neither those credentials nor network access.

## Frontend and other post-boundary changes

Strategy Lab adds Research Agent and Market Concepts areas, baseline/dataset
controls, evidence breakdowns, hypotheses, committee reviews, loop authorization,
trials, candidate freezing, cost/regime/simplification review, validation, decisions,
manager guidance and isolated-draft controls. Run Viewer adds explicit source and
manifest export. Existing chart/Trade Review foundations from the boundary remain
in place; this phase did not replace the chart library or retune strategies.

The broader working tree also adds verified MT5 futures-market-data mapping and
diagnostics, an explicitly selected Massive/MT5 NQ route, a read-only Robinhood
holdings adapter with discovered allowlisted tools, and truthful Journal automation
provenance/filtering. Details and live limitations are in
[MT5/Robinhood integration](MT5_ROBINHOOD_INTEGRATION.md). Live terminal entitlement,
Robinhood response shapes and authenticated comparison remain user acceptance
work. No order-placement capability was added. User-added research strategy files
are inventoried, not asserted to have been designed or optimized by this phase.

## How to use and manually test

1. Keep Docker Desktop in Linux-container mode and start Ledger normally. Use one
   backend instance per database. Back up application data before upgrading.
2. From `backend`, build the allowlisted image once:
   `.venv/Scripts/python.exe -B tools/build_research_sandbox.py`.
   Save its JSON manifest. Rebuild if Ledger reports a stale sandbox image.
3. Configure a normal single-symbol Backtest. Open Research Agent, create a project,
   register development coverage including warmup and separate genuine holdout dates.
4. Queue the frozen baseline and inspect sample sizes, winner retention and missing
   diagnostics. Preregister a numeric hypothesis manually, or explicitly consent
   to committee review with a configured model and budget. Approve its trial.
5. After the unchanged control and development cells finish, inspect robustness and
   freeze a candidate. This stops the autonomous numeric loop.
6. Create a standalone generated `Strategy` draft through the existing quarantine
   API; do not put it into the normal strategies directory. It must have one concrete
   Strategy subclass, a unique `research_child_...` key, declared parameters and
   only imports available in the allowlisted image. Store it with:
   `POST /api/strategy-lab/research-agent/{project}/candidates/{candidate}/code-drafts`
   using `request_key`, `registry_key`, `source`, `rationale`, and acknowledgement
   `Store this source as an inert quarantined draft; no execution or activation`.
   Obtain project/candidate IDs from their API records or the expanded UI evidence.
7. Reopen the frozen candidate. In **Quarantined strategy sandbox**, select the draft,
   enter feature-off control parameters and feature-on candidate parameters as JSON,
   check consent and choose **Run isolated checks**. The UI uses a 120-second limit.
   The API `/code-drafts/{draft}/sandbox` accepts the same two parameter objects,
   `timeout_seconds` and acknowledgement
   `Run this quarantined source in Docker on frozen development data only`.
8. Observe `PREPARATION`, `CONTROL_PARITY`, `CANDIDATE`, `CAUSALITY_PREFIX` and the
   terminal evidence. A mismatched control must fail before candidate evaluation;
   inspect `first_divergence`. Repeat approval must return the same attempt.
9. Test **Cancel isolated run**, navigate away/reopen and confirm terminal status.
   Use an isolated test database for crash/hostile tests, not the production server.
   The automated EOF, forced coordinator-process death and recovery tests exercise backend-death cleanup safely.
10. Inspect hashes, resource samples, N and warnings. Sandbox evidence is development
    research only. Parent validation approval and research acceptance do not promote
    or validate this generated child automatically.
11. To run real acceptance from `backend` in PowerShell:
    `$env:LEDGER_TEST_DOCKER='1'` then
    `.venv/Scripts/python.exe -B -m pytest tests/test_research_sandbox.py tests/test_research_sandbox_docker.py tests/test_sandbox_research_loop.py -q`.
    With that variable set, run `Verify-Ledger.ps1` from the repo for full verification.
12. Check `docker ps -a --filter label=com.ledger.research.sandbox`. No abandoned
    research containers should remain. Do not prune unrelated user containers.

## Limitations and deferred work

- Generated code is an explicitly approved development continuation. Automatic
  model code-authoring, child activation/promotion and generated-child holdout
  orchestration are not silently added to the numeric research loop.
- Only the bundled contract, indicators and concepts are available. Arbitrary
  strategy-module imports, external dependencies and diagnostic-history side
  channels fail closed. Parent-specific reporting metadata can cause strict parity
  rejection; it is not ignored to manufacture a pass.
- One symbol, 10,000 aggregate bars and a bounded deadline are intentional initial
  safety limits. Full-prefix JSON transfer prioritizes correctness over large-history
  throughput. Exceeding a limit fails; it does not silently sample a dataset.
- Prefix replay checks a finite primary-bar prefix. It is not a mathematical proof,
  a guarantee against hard-coded future facts or a profitability claim.
- Generated results are stored with their sandbox attempt, not automatically
  promoted into ordinary selectable strategies or a validation grant.
- Docker image/data retention and full portable market-data archival are operator
  responsibilities. Source hashes alone cannot replay missing market history.
- Live provider/LLM acceptance, MT5 expired-contract coverage and Robinhood access
  remain external prerequisites. No live credential was read for this verification.
- Existing frontend bundle-size and Starlette/httpx deprecation advisories remain.
- Unrelated pre-existing staged strategy edits and whitespace are preserved.

## Before / after

| Before boundary | Current capability |
| --- | --- |
| Manual strategy research and saved runs | Durable research projects, dataset/debt registry and bounded experiment workflow |
| Human interpretation of metrics | Deterministic evidence plus optional constrained three-role critique |
| Ad hoc candidate testing | Frozen candidates, declared cost/regime/ablation checks and candidate-bound validation |
| Strategy-specific detection helpers | Optional versioned Market Concepts and independent causal visual audits |
| Partial source identity | Captured loaded-source archives and explicit reproducibility manifests |
| Generated source could only remain inert | Quarantine → explicit Docker checks → retained development evidence |
| Backend lifetime could govern worker lifetime | Independent guardian, owned-container cleanup and durable restart reconciliation |

## Final verification and file inventory

Final counts, image identity, browser checks and exact file inventory are recorded
below after verification of the final working tree.

### Final verification: 2026-10-10

The complete verification finished against the final application/test tree; only
closeout documentation was edited afterwards. `Verify-Ledger.ps1` ran with
`LEDGER_TEST_DOCKER=1` and isolated output outside the repository.

| Check | Final result |
| --- | --- |
| Complete backend suite | **1,062 passed, 0 failed, 0 errors, 0 skipped**; 427.46 seconds |
| Frontend suite | **128 passed, 0 failed, 0 skipped** |
| Production frontend build | **Passed**; 151 modules; 1.18 seconds |
| Sandbox protocol/unit tests (included above) | **16 passed** |
| Real Docker security/lifecycle suite (included above) | **18 passed** |
| Real Docker mocked research-loop integration (included above) | **7 passed** |
| Browser acceptance | **Passed at 1024, 1440 and 1920 px**; Research Agent, concept audits and source archive; mocked API, no runtime errors or page overflow |
| Final Ledger research containers | **Zero**, confirmed with Docker label-filtered listing |

There are 41 new sandbox tests in total, including 25 real-Docker tests.
The final full run includes the stderr-flood fixture missing from the prior
1,061-test run. The independent focused security/lifecycle run also passed all
18 cases. Browser results were obtained on the same final frontend application
code before closeout; browser acceptance does not assert live LLM/provider access.

Final artifacts:

- `C:/Users/jamie/Project/research-docker-acceptance-final/verification.log`
- `C:/Users/jamie/Project/research-docker-acceptance-final/backend.xml`
- `C:/Users/jamie/Project/research-docker-acceptance-final/frontend/`

The JUnit report confirms zero errors/failures/skips and the 16/18/7 sandbox
subsuite counts. Its Windows path was corrected by moving the generated report
outside the repository after verification; no application/test changes followed.

Sandbox image: `sha256:2e59a1c8f03cac1c57549325434bc01fab969f4d92a06cf9e797826dd912bc86`.
Base: `python@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1`.

Final Docker inspection found six unrelated stopped containers still present:
`etsydashboard-v013-postgres-1`, `etsydashboard-postgres-1`,
`odysseus-odysseus-1`, `odysseus-searxng-1`, `odysseus-chromadb-1`,
and `odysseus-ntfy-1`. No unrelated container was removed or operated on during
closeout; the owned-cleanup regression explicitly proves another owner's
container is preserved. No Docker prune was performed. The sandbox image is
retained for use and is not an orphan container.

Non-blocking advisories: backend Starlette/httpx deprecation warning and Vite's
large-bundle warning (939.58 kB JavaScript, 274.94 kB gzip). Full-tree
`git diff HEAD --check` still reports pre-existing trailing whitespace in
`backend/app/backtesting/strategies/turtle_donchian_research_v1.py:134`.
It was intentionally left untouched; the diff excluding user strategy files,
and the shared strategy base file, pass whitespace checks.

All changes remain uncommitted, including pre-existing staged/user strategy work.
The inventory below lists every changed/new application, test and documentation
file relative to `afb73e9`: 53 modified files, 114 new files, no deletions.
Untracked `backend/research_output/` data remains untouched and is not counted
as source. No commit, staging, credential access or history rewrite was performed.


## Docker references used

The restrictions follow the official Docker documentation for
[container run](https://docs.docker.com/reference/cli/docker/container/run/),
[runtime limits](https://docs.docker.com/engine/containers/run/) and
[engine security](https://docs.docker.com/engine/security/).
Actual acceptance tests additionally inspect and exercise the local Engine 29.6.1
runtime; documentation alone is not treated as proof of isolation.

## Exact post-boundary application/test/document inventory

This inventory includes pre-existing staged/user changes and earlier Research Agent work,
not just files authored during Docker continuation. Untracked research output data
is excluded and untouched. No obsolete-file purge was performed in this phase.

### Modified tracked files

- `.env.example`
- `backend/app/api/data.py`
- `backend/app/api/router.py`
- `backend/app/api/strategy_lab.py`
- `backend/app/backtesting/context.py`
- `backend/app/backtesting/engine.py`
- `backend/app/backtesting/strategies/base.py`
- `backend/app/backtesting/strategies/open_session_atr_breakout_research_v1.py`
- `backend/app/backtesting/strategies/turtle_donchian_research_v1.py`
- `backend/app/brokers/executions.py`
- `backend/app/brokers/metatrader5.py`
- `backend/app/brokers/profiles.py`
- `backend/app/core/config.py`
- `backend/app/core/journal_analytics.py`
- `backend/app/data/futures.py`
- `backend/app/data/instruments.py`
- `backend/app/data/providers/massive_futures.py`
- `backend/app/services/backtest.py`
- `backend/app/services/backtest_jobs.py`
- `backend/app/services/broker_connections.py`
- `backend/app/services/broker_scheduler.py`
- `backend/app/services/container.py`
- `backend/app/services/journal.py`
- `backend/app/services/market_data.py`
- `backend/app/services/research_runner.py`
- `backend/app/services/strategy_workspace.py`
- `backend/app/storage/backtest_run_repository.py`
- `backend/app/storage/broker_sync_repository.py`
- `backend/app/storage/database.py`
- `backend/app/storage/journal_repository.py`
- `backend/app/storage/portfolio_broker_repository.py`
- `backend/tests/conftest.py`
- `backend/tests/test_backtest_jobs.py`
- `backend/tests/test_data_api.py`
- `backend/tests/test_journal_v2.py`
- `backend/tests/test_mt5_import.py`
- `backend/tests/test_parent_research.py`
- `backend/tests/test_research_infrastructure.py`
- `docs/README.md`
- `frontend/src/api/client.js`
- `frontend/src/features/brokers/BrokerProfilesPanel.jsx`
- `frontend/src/features/brokers/brokerConnectionUtils.js`
- `frontend/src/features/journal/JournalFilters.jsx`
- `frontend/src/features/journal/TradesView.jsx`
- `frontend/src/features/journal/journalTable.js`
- `frontend/src/features/portfolio/BrokerPortfolioPanel.jsx`
- `frontend/src/features/portfolio/brokerPortfolioUtils.js`
- `frontend/src/features/settings/SettingsPage.jsx`
- `frontend/src/features/strategy-lab/StrategyLabPage.jsx`
- `frontend/src/features/strategy-lab/strategyRefresh.js`
- `frontend/tests/brokerConnections.test.js`
- `frontend/tests/brokerPortfolio.test.js`
- `frontend/tests/strategyRefresh.test.js`

### New files (staged additions and untracked source/tests/docs)

- `backend/app/api/research_agent.py`
- `backend/app/backtesting/strategies/REVIEW_NOTES.md`
- `backend/app/backtesting/strategies/TEST_SETTINGS.txt`
- `backend/app/backtesting/strategies/amn_structure_retest_research_v1.py`
- `backend/app/backtesting/strategies/gao_intraday_momentum_research_v1.py`
- `backend/app/backtesting/strategies/noise_area_intraday_momentum_research_v1.py`
- `backend/app/backtesting/strategies/poc_reclaim_retest_research_v1.py`
- `backend/app/backtesting/strategies/qqq_opening_bias_5m_research_v1.py`
- `backend/app/backtesting/strategies/vwap_mean_reversion_research_v1_reattached.py`
- `backend/app/backtesting/strategies/vwap_trend_confirmation_htf_research_v3.py`
- `backend/app/backtesting/strategies/vwap_trend_confirmation_quality_research_v5.py`
- `backend/app/backtesting/strategies/vwap_trend_confirmation_research_v2.py`
- `backend/app/backtesting/strategies/vwap_trend_research_v1.py`
- `backend/app/brokers/execution_provider.py`
- `backend/app/brokers/robinhood.py`
- `backend/app/core/automation.py`
- `backend/app/data/calendar_front.py`
- `backend/app/data/providers/metatrader5.py`
- `backend/app/market_concepts/__init__.py`
- `backend/app/market_concepts/base.py`
- `backend/app/market_concepts/benchmark.py`
- `backend/app/market_concepts/builtins.py`
- `backend/app/market_concepts/registry.py`
- `backend/app/research_agent/__init__.py`
- `backend/app/research_agent/access.py`
- `backend/app/research_agent/analysis.py`
- `backend/app/research_agent/candidate_checks.py`
- `backend/app/research_agent/candidates.py`
- `backend/app/research_agent/committee.py`
- `backend/app/research_agent/concept_audits.py`
- `backend/app/research_agent/costs.py`
- `backend/app/research_agent/decisions.py`
- `backend/app/research_agent/diagnostics.py`
- `backend/app/research_agent/feedback.py`
- `backend/app/research_agent/hypotheses.py`
- `backend/app/research_agent/llm.py`
- `backend/app/research_agent/loop.py`
- `backend/app/research_agent/manager.py`
- `backend/app/research_agent/quarantine.py`
- `backend/app/research_agent/regimes.py`
- `backend/app/research_agent/repository.py`
- `backend/app/research_agent/sandbox.py`
- `backend/app/research_agent/sandbox_guardian.py`
- `backend/app/research_agent/sandbox_image.py`
- `backend/app/research_agent/sandbox_runs.py`
- `backend/app/research_agent/sandbox_wire.py`
- `backend/app/research_agent/sandbox_worker.py`
- `backend/app/research_agent/simplification.py`
- `backend/app/research_agent/spending.py`
- `backend/app/research_agent/trials.py`
- `backend/app/research_agent/validation.py`
- `backend/app/research_agent/workflow.py`
- `backend/app/services/futures_diagnostics.py`
- `backend/app/storage/reproducibility.py`
- `backend/app/storage/research_retention.py`
- `backend/app/storage/strategy_source_archive.py`
- `backend/tests/test_code_quarantine.py`
- `backend/tests/test_concept_audits.py`
- `backend/tests/test_concept_migration_checks.py`
- `backend/tests/test_futures_diagnostics.py`
- `backend/tests/test_journal_automation.py`
- `backend/tests/test_market_concepts.py`
- `backend/tests/test_mt5_market_data.py`
- `backend/tests/test_reproducibility.py`
- `backend/tests/test_research_candidates.py`
- `backend/tests/test_research_committee.py`
- `backend/tests/test_research_costs.py`
- `backend/tests/test_research_decisions.py`
- `backend/tests/test_research_diagnostics.py`
- `backend/tests/test_research_feedback.py`
- `backend/tests/test_research_foundation.py`
- `backend/tests/test_research_hypotheses.py`
- `backend/tests/test_research_loop.py`
- `backend/tests/test_research_manager.py`
- `backend/tests/test_research_regimes.py`
- `backend/tests/test_research_retention.py`
- `backend/tests/test_research_sandbox.py`
- `backend/tests/test_research_sandbox_docker.py`
- `backend/tests/test_research_simplification.py`
- `backend/tests/test_research_spending.py`
- `backend/tests/test_research_suggestions.py`
- `backend/tests/test_research_trials.py`
- `backend/tests/test_research_validation.py`
- `backend/tests/test_robinhood_portfolio.py`
- `backend/tests/test_sandbox_research_loop.py`
- `backend/tests/test_strategy_source_archive.py`
- `backend/tools/build_research_sandbox.py`
- `backend/tools/export_saved_run_trades.py`
- `backend/tools/vwap_trade_feature_research.py`
- `docs/MT5_ROBINHOOD_INTEGRATION.md`
- `docs/RESEARCH_AGENT_FOUNDATION.md`
- `docs/RESEARCH_AGENT_MAJOR_UPDATE_2026-10.md`
- `frontend/src/features/settings/FuturesDiagnosticsPanel.jsx`
- `frontend/src/features/strategy-lab/ConceptAudits.jsx`
- `frontend/src/features/strategy-lab/ResearchCandidates.jsx`
- `frontend/src/features/strategy-lab/ResearchCommittee.jsx`
- `frontend/src/features/strategy-lab/ResearchCosts.jsx`
- `frontend/src/features/strategy-lab/ResearchDecision.jsx`
- `frontend/src/features/strategy-lab/ResearchEvidence.jsx`
- `frontend/src/features/strategy-lab/ResearchFoundations.jsx`
- `frontend/src/features/strategy-lab/ResearchHypotheses.jsx`
- `frontend/src/features/strategy-lab/ResearchLoop.jsx`
- `frontend/src/features/strategy-lab/ResearchManager.jsx`
- `frontend/src/features/strategy-lab/ResearchRegimes.jsx`
- `frontend/src/features/strategy-lab/ResearchSandbox.jsx`
- `frontend/src/features/strategy-lab/ResearchSimplification.jsx`
- `frontend/src/features/strategy-lab/ResearchTrials.jsx`
- `frontend/src/features/strategy-lab/ResearchValidation.jsx`
- `frontend/src/features/strategy-lab/researchSandbox.js`
- `frontend/tests/browser/broker-integrations.mjs`
- `frontend/tests/browser/concept-audits.mjs`
- `frontend/tests/browser/research-foundations.mjs`
- `frontend/tests/browser/source-archive.mjs`
- `frontend/tests/researchSandbox.test.js`

### Deleted tracked files

None.
