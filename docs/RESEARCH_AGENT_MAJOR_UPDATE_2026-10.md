# Ledger Research Agent major update — October 2026

## Boundary and evidence

Boundary: **`afb73e9f4b0679fd5a7c8b10498289b7a8fd610b`**, committed
2026-10-05, “Keep trade review autoscaling local to visible price action”.
This was the comparison boundary when the foundation report was prepared. The previous
Research Agent foundation handoff accumulated subsequent uncommitted checkpoints;
it was not another committed release. This document consolidates those changes
and the Docker continuation. It does not attribute pre-existing user strategy
files to the Docker implementation. The file inventory below is derived from
`git diff HEAD` and untracked application/test/document files.

## Executive summary

### Latest continuation: campaign preparation, Code Author, bounded robustness and primary UI (2026-10-11)

Continuation boundary: committed Research Agent foundation **`8d73ebe`**. The
earlier `afb73e9` boundary remains the boundary for the complete major update.
The sections below describing earlier checkpoints are historical snapshots;
this section takes precedence for current campaign behavior.

**This is a verified increment toward checkpoints 3–6, not a claim that the
entire autonomous-research specification is complete.**

Delivered in this continuation:

- Provider-backed preparation through the existing durable cache warmer, with
  frozen ranges/provider identity, bounded retries, restart recovery and guards
  before actual fetches. Timestamp-only discovery also works from existing cache.
- Durable single launch: preparation, baseline queueing, optional numeric cycles,
  and one optional structural child per family progress in the backend.
- A separate first-development-session reference baseline for generated-code
  checks. The original full-period baseline is retained. Reference projects share
  the existing dataset IDs and cannot create a fresh holdout or count as an
  accepted candidate. The 10,000-bar sandbox limit is unchanged.
- Researcher → Devil → Manager → Code Author, using structured model responses.
  The Manager may reject before source generation. Four calls and their maximum
  configured cost are reserved in the existing `agent_reviews` ledger before
  calls occur. Numeric reviews and authoring cannot spend separate hidden budgets.
- Archived parent source only: no substitution from a changed file. A bounded
  parent module and verified development evidence go to the model under explicit
  source-sharing consent. Generated Python is parsed/stored as inert quarantine
  text; it is never imported into Ledger's backend registry.
- Director-authorized Docker dispatch with frozen parent/draft identities and
  fixed feature-off/feature-on parameters. Existing engine parity, prefix checks,
  container restrictions, guardian and failure cleanup remain mandatory.
- Parent/child path comparison records retained, removed and introduced trades,
  including lost large and session-close winners. A research report shows sample
  sizes, failures, reservations and source identity without ranking strategies.
- New structural campaigns freeze the first seven calendar days (or the whole
  shorter interval) of each internal development window before dispatch. Up to
  three windows are supported. Each runs trusted parent, generated control,
  generated child and prefix check at normal and doubled engine costs. Samples
  have independent capital and are never combined into portfolio returns.
- Primary **Research Agent → Campaigns** UI, with explicit costs and model/code
  permissions, lifecycle controls and report. **Advanced projects** retains the
  prior project workflow; Market Concepts remains separate.

Checkpoint status:

| Checkpoint | Current status |
| --- | --- |
| 3: automatic data/queue preparation | Implemented for bounded US-equity intraday cached/provider history; provider completeness is not certified |
| 4: Code Author / structural execution | Core single-child author-to-Docker path implemented and tested; broader structural iteration and dependency reconstruction remain incomplete |
| 5: research decisions / robustness | Bounded multi-window/cost checks, report and deterministic warnings implemented; full-period child robustness, acceptance and abandonment policy remain incomplete |
| 6: primary UI / end-to-end acceptance | Primary UI and fixture browser checks implemented; live-model quality benchmarks and overnight acceptance remain incomplete |

#### Authority, recovery and budgets

Campaign policies and launch configuration are immutable. Automatic preparation
has a fixed deadline and consumes the campaign's existing time allowance. Every
provider chunk rechecks campaign status, protected dataset overlaps and provider
namespace; the low-level fetch guard also checks any cache-driven range expansion.
Rate-limit retries preserve retry deadlines and retain their retry count across
restart. Failures preserve already cached data and prior results.

The Director reserves baseline/numeric/reference/sandbox simulations, model calls,
children and compute allowances before queueing work. Reference dates are the
first declared development session, selected before results. They are not a
profitable subperiod selected after observing performance. Original long-period
results remain immutable and distinct from the reference result.

The additional robustness samples consume **8 simulations per window**, above
the four anchor sandbox simulations. Including the original and reference
baselines, structural work reserves **6 + 8N** simulations per family (30 at the
default three windows), plus any numeric cycles. Insufficient budgets fail before
dispatch; QUICK's 24 simulations cannot fund the default structural workload.
The existing single-symbol/10,000-bar limit and overall maximum 600-second sandbox
deadline are unchanged and cover all samples, not each sample separately.
History is checked against the same development firewall before fetching and
after preparation. A wrong-window primary frame, changed provider or changed
data between cost scenarios stops the attempt. Failed samples retain prior
evidence and are not automatically retried. Zero configured costs remain zero
under doubling and explicitly produce a warning, not a cost-stress claim.
Old immutable approvals without windows keep their original execution scope.

Authoring runs on a bounded backend thread. Pause, deadline, source changes and
model/pricing changes prevent subsequent calls or Docker dispatch. Restart marks
an interrupted paid author attempt interrupted; no silent paid retry occurs.
Sandbox restart recovery keeps its existing interrupted-attempt/no-retry policy.
Known active queue requests retain their idempotency identities. Browser polling
only observes progress; it is not the coordinator.

No live orders, automatic activation, host-side generated Python, extra Docker
mounts, networking, privilege or sandbox fallback have been introduced.

#### Storage changes

No destructive schema migration. Initialization remains additive/idempotent.
Campaign tables (`agent_campaigns`, `agent_campaign_actions`,
`agent_campaign_events`) and shared `agent_dataset_memberships` were introduced
by this uncommitted Director continuation. Preparation, launch and structural
phase state live in campaign JSON. Code Author uses the existing `agent_reviews`
table, marked `kind=CODE_AUTHOR`; source remains in `agent_code_drafts`.
Reference snapshots use `agent_candidates` with `kind=CONTROL_REFERENCE` and
`state=REFERENCE`; existing validation gates reject them. Docker comparisons are
additive fields in `agent_sandbox_runs`. Journal/broker schemas are unchanged.
Window plans are additive campaign JSON; per-sample results, fingerprints,
control/prefix evidence and provenance are additive sandbox JSON. This robustness
increment adds no table or schema migration.

#### Current limits and next work

1. New generated children receive an anchor-session check and **bounded samples
   from preregistered development windows**, at normal and doubled costs. Older
   approvals retain their original first-session scope. Passing these checks is
   neither full-history performance nor proof of universal causality. The sample
   boundaries reset indicators and capital; insufficient history may reject
   signals or fail parity. Full-period robustness, simplification and
   candidate-bound holdout orchestration remain incomplete. Reports retain
   `ROBUSTNESS_REQUIRED`; no automatic acceptance is inferred.
2. The author receives one archived parent module, capped at 25 KB; evidence plus
   source is capped at 60 KB before the existing adapter's 90 KB request limit.
   Archived helper modules are not recursively assembled. Complex inherited
   strategies may fail interface/control parity. This has **not** established
   that a real LLM can correctly reconstruct the VWAP V5 dependency chain.
3. Automatic discovery uses a fixed registered-family catalog, not literature
   search, novel-idea synthesis or a survivorship-free stock universe. Novel idea
   mode fails explicitly rather than substituting an unrelated strategy.
4. Session dates are observed timestamps, not a certified exchange completeness
   check. Only supported US-equity intraday history is automatically prepared.
   A disjoint cache interval that forces the market service to fetch beyond the
   authorized range is rejected; it is not silently bridged.
5. The current launch UI uses regular sessions, risk-percent sizing and explicit
   per-order/bps cost inputs. Strategy-specific defaults remain unchanged.
   Failed preparations require investigating coverage/configuration; the launch
   is not silently widened, repriced or retried with different settings.
6. Numeric/structural queues are bounded, not an open-ended autonomous discovery
   process. No autonomous child promotion, acceptance or deployment is claimed.
7. External LLM/provider acceptance, the intelligence/VWAP reasoning benchmarks,
   compressed campaign soak and real overnight/24-hour soak remain outstanding.

#### Manual acceptance for this increment

1. Start Ledger and open **Backtest → Research Agent → Campaigns**.
2. Choose **Find strategies** or **Improve a strategy**, US-equity symbol(s),
   primary timeframe and a budget preset. Confirm realistic account/cost values.
3. Choose cached history or bounded provider preparation (four calendar years).
   Provider preparation requires the normal configured historical-data provider.
4. For a no-LLM smoke, leave model permission off, authorize the settings and
   start. Close/reopen the page; inspect fixed plans, baseline runs and the report.
5. For numeric research, configure the existing model enable/key/model/pricing
   settings locally and authorize development evidence sharing. Select 1–2
   numeric cycles within the preset budget.
6. For structural work, first ensure the existing approved sandbox image is
   available, enable source-sharing/child permission, and use a simple strategy
   whose saved baseline has an archived source module. Observe reference run,
   Researcher/Devil/Manager/Author evidence, draft hash and Docker checks. Expect
   unsupported source/dependency/parity cases to stop rather than execute on host.
7. Pause/resume, stop after current and cancel; confirm no next family/model call
   starts after authority is revoked. Restart during authoring/Docker work and
   confirm interrupted paid/generated attempts are not automatically repeated.
8. Inspect N, lost winners, new entries and `ROBUSTNESS_REQUIRED`. Do not interpret
   bounded development samples as a profitable full-period or validated strategy.
   Expand each family's **development windows and cost checks** table. Check dates,
   normal/2x costs, N, average R, total R and PF separately. Zero-cost scenarios
   should show a warning. Use STANDARD or a sufficient explicit budget for the
   default structural workload; do not weaken costs to force a pass.

#### Final bounded-robustness verification (2026-10-11)

This is the final verification for the current working tree, superseding the
earlier 1,190-test increment below. No application or test edits followed the run.

| Check | Final result |
| --- | --- |
| Full backend, `LEDGER_TEST_DOCKER=1`, `python -B -m pytest tests -q -p no:cacheprovider`, isolated basetemp and JUnit | **1,206 passed, 0 failures/errors/skips**, 560.60 seconds |
| Real Docker security/lifecycle | **18 passed**, included above |
| Docker research-loop tests, including wrong-window and locked-holdout rejection | **9 passed**, included above |
| Reference / Code Author / complete multi-window campaign Docker integrations | **3 passed**, included above |
| All real Docker tests | **30 passed**, not additional to backend total |
| Sandbox protocol/unit tests | **16 passed**, included in backend total |
| All frontend, `node --test tests/*.test.js` | **132 passed**, no failures/skips |
| Production build, `node verify-build.mjs` | **Passed**, native exit 0, 154 modules |
| Campaign browser fixture, including expanded window/cost table | **Passed at 1024 / 1440 / 1920px**, no runtime errors or page overflow |
| Docker inventory | **Zero Ledger research containers**; the same six unrelated stopped containers unchanged |
| Diff whitespace, changed/new source whitespace and handoff links | **Passed** |

This increment adds **16 backend cases**: 12 robustness contract/execution tests,
one campaign-budget test, one report test and two real-Docker failure/firewall
tests. The existing complete campaign test now also exercises two independent
development windows at normal and doubled costs, with control/prefix gates.
Tests cover frozen chronology, run reservations, immutable authorization,
cost forwarding, data changes, parity/prefix failures, cancellation propagation,
partial evidence, wrong-window data, protected-history rejection and zero-cost
warnings. No live model or historical-data provider was called.

Docker preflight initially returned `No such image` for the sandbox tag while
listing it and resolving its existing immutable image ID. Reapplying that tag to
the **same existing image** restored lookup; the targeted real-Docker test and
the final full suite passed afterward. No image rebuild, security bypass,
automatic retry or application fallback was introduced. The daemon's underlying
tag-lookup inconsistency remains unexplained.

The unchanged sandbox image is
`sha256:2e59a1c8f03cac1c57549325434bc01fab969f4d92a06cf9e797826dd912bc86`.
Existing advisories remain: one Starlette/httpx deprecation and the Vite chunk
size warning (main JS approximately 954 KB). Browser acceptance used fixture
APIs; the isolated browser/server were stopped afterward.

Artifacts: `C:/Users/jamie/Project/director-robustness-final-20261011/backend.log`,
`backend.xml`, and `frontend/`; screenshots:
`C:/Users/jamie/Project/director-robustness-browser-20261011/campaign-{width}.png`.
All continuation work remains uncommitted: **22 tracked modifications and 29
new files**, no deletions. The inventory below covers the whole continuation.

#### Previous verified increment (before bounded robustness)

Final exact-tree verification on 2026-10-11:

| Check | Result |
| --- | --- |
| Full backend `python -B -m pytest tests -q -p no:cacheprovider` with `LEDGER_TEST_DOCKER=1`, isolated basetemp and JUnit XML | **1,190 passed, 0 failures/errors/skips**, 513.64 seconds |
| Real Docker security/lifecycle | **18 passed**, included in backend total |
| Existing Docker research loop | **7 passed**, included in backend total |
| New reference / author / full campaign real-Docker integrations | **3 passed**, included in backend total |
| All real-Docker cases | **28 passed**, not additional to backend total |
| All frontend `node --test tests/*.test.js` | **132 passed**, 0 failed/skipped |
| Production `node verify-build.mjs` | **Passed**, native exit 0, 154 modules |
| Browser campaign fixture smoke | **Passed at 1024 / 1440 / 1920px** |
| `git diff --check`, changed/new source whitespace and two handoff documents' relative links | **Passed** |
| Final Docker inspection | **0 Ledger research containers**; same six unrelated stopped container IDs/statuses |

New tests since the 1,138-backend discovery continuation: preparation **13**,
reference **5**, Code Author **11**, structural campaign **6**, launch **10**,
report **7**: **52 new backend cases**. Frontend adds **4** campaign utility cases.

The first full run recorded **1,182 passed / 1 failed**: Docker image inspection
briefly returned `No such image` through the sandbox CLI even though the local
image appeared in Docker's listing. Credential-free inspection subsequently
succeeded, and the affected real-Docker test passed without an application
change. That first run did not include the seven subsequently added report
checks. The final complete repeat above includes them and has zero failures.
The cause of the transient Docker daemon response was not established; no retry,
security bypass or host-execution fallback was added.

Advisories: one existing Starlette/httpx deprecation warning; Vite's existing
large-chunk warning. Browser checks exercised launch, pause/resume, report and
Advanced projects navigation with no runtime errors or page overflow. They used
fixture APIs, not a real LLM/provider. The isolated browser/server were stopped.

Artifacts: `C:/Users/jamie/Project/director-final-confirmed-20261011/backend.log`,
`backend.xml` and isolated `frontend/` build. Browser screenshots are in
`C:/Users/jamie/Project/director-browser-20261011/`.
All application/test changes preceded the final complete run; only documentation
was finalized afterward. Earlier 1,138/128 counts below are historical.


#### Exact uncommitted continuation inventory (against `8d73ebe`)

Modified tracked files (22):

- `backend/app/api/research_agent.py`
- `backend/app/api/router.py`
- `backend/app/research_agent/access.py`
- `backend/app/research_agent/candidate_checks.py`
- `backend/app/research_agent/candidates.py`
- `backend/app/research_agent/decisions.py`
- `backend/app/research_agent/hypotheses.py`
- `backend/app/research_agent/loop.py`
- `backend/app/research_agent/regimes.py`
- `backend/app/research_agent/repository.py`
- `backend/app/research_agent/sandbox_runs.py`
- `backend/app/research_agent/workflow.py`
- `backend/app/services/backtest_jobs.py`
- `backend/app/services/container.py`
- `backend/app/services/market_warmup.py`
- `backend/tests/test_sandbox_research_loop.py`
- `docs/RESEARCH_AGENT_FOUNDATION.md`
- `docs/RESEARCH_AGENT_MAJOR_UPDATE_2026-10.md`
- `frontend/src/api/client.js`
- `frontend/src/features/strategy-lab/ResearchCandidates.jsx`
- `frontend/src/features/strategy-lab/ResearchFoundations.jsx`
- `frontend/src/features/strategy-lab/StrategyLabPage.jsx`

New files (29):

- `backend/app/api/research_campaigns.py`
- `backend/app/research_agent/author.py`
- `backend/app/research_agent/campaign_policy.py`
- `backend/app/research_agent/campaign_projects.py`
- `backend/app/research_agent/campaign_report.py`
- `backend/app/research_agent/campaigns.py`
- `backend/app/research_agent/dataset_planner.py`
- `backend/app/research_agent/director.py`
- `backend/app/research_agent/discovery.py`
- `backend/app/research_agent/launch.py`
- `backend/app/research_agent/preparation.py`
- `backend/app/research_agent/robustness.py`
- `backend/app/research_agent/structural.py`
- `backend/tests/test_campaign_launch.py`
- `backend/tests/test_campaign_preparation.py`
- `backend/tests/test_campaign_projects.py`
- `backend/tests/test_campaign_report.py`
- `backend/tests/test_campaign_structural.py`
- `backend/tests/test_research_author.py`
- `backend/tests/test_research_campaigns.py`
- `backend/tests/test_research_director.py`
- `backend/tests/test_research_discovery.py`
- `backend/tests/test_research_references.py`
- `backend/tests/test_research_robustness.py`
- `frontend/src/features/strategy-lab/AutonomousResearch.jsx`
- `frontend/src/features/strategy-lab/ResearchHome.jsx`
- `frontend/src/features/strategy-lab/campaignView.js`
- `frontend/tests/browser/campaign-smoke.mjs`
- `frontend/tests/campaignView.test.js`

No tracked files were deleted. These counts include earlier Director work in the current working tree, not only this turn.

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

## Autonomous Research Director: discovery continuation (2026-10-11)

**PARTIAL: checkpoints 3–6 are not complete.** Checkpoint 2 remains the last
completed checkpoint. The current continuation adds automatic preparation from
existing cache evidence; it does not claim automatic code authoring or complete
minimal-prompt research.

### Implemented in this continuation

- `POST /api/strategy-lab/research-campaigns/{id}/auto-prepare` selects a bounded
  queue from registered research families and freezes the existing chronological
  dataset plan without asking an operator to construct a session manifest.
- Selection follows an explicit deterministic catalog, not historical performance:
  VWAP continuation, opening range, VWAP reversion, Donchian. Only registered
  entries whose declared primary timeframe matches the policy are eligible.
  Improve mode uses the requested registered strategy. Novel-idea mode fails
  explicitly instead of silently substituting an unrelated catalog strategy.
- Coverage uses the currently routed provider namespace and projects only the
  cached Parquet **timestamp** column. It reads no prices, volume or saved
  performance, makes no provider requests, and invents no weekday/session dates.
  Current/future New York dates are excluded, with the existing UTC-date guard
  retained. Timestamp identity and observed session boundaries are frozen.
- Discovery is bounded to two million timestamps. Unreadable/missing cache,
  invalid/duplicate timestamps, concurrent file replacement, unsupported identity,
  and insufficient history fail explicitly. There is no truncated or fabricated
  success result. Resolved paths must remain within the configured cache root.
- Automatically provisioned projects bind to the planned provider namespace before
  their first market-data request. A feed change fails the existing access gate.
- Discovery metadata and frozen plans are saved together. Repeating automatic
  preparation returns the original plan; it does not move boundaries or create
  another project/holdout. Existing exposure checks and transactional provisioning
  still apply.

### Scope and remaining work

Automatic cache discovery currently supports US-equity intraday timestamps
(1m/5m/15m/30m/1h). Cached observed dates are **not** a certified exchange calendar:
missing whole sessions, intraday gaps and early-close completeness are not inferred.
There is no new provider download loop, futures session planner, daily-bar session
adapter or point-in-time equity universe. Any universe-wide historical conclusion
remains subject to survivorship bias. The advanced operator-manifest path remains.

The inspected source contains no numbered definition of checkpoints 3–6. The
proposed continuation breakdown is 3: automatic data/queue preparation; 4: Code
Author and structural Docker iteration; 5: research decisions/robustness/reporting;
6: primary UI and end-to-end acceptance. This is a work plan, not a completion claim.

An important checkpoint-4 integration constraint remains unresolved: current
Docker execution requires a verified frozen parent candidate and at most **10,000
aggregate supplied bars**. Default campaigns span hundreds of sessions. Do not
raise the sandbox limit, silently truncate a full-period parent, or compare a
shortened child against a different parent's result. The next implementation must
create an explicitly bounded, development-only parent run with matching source,
configuration and data fingerprint, preserve the full-period evidence, and use
that exact anchor for parity and prefix checks. Current candidate freezing is
trial-variant based; extending this ownership must preserve the candidate,
validation and saved-result contracts. None of those contracts was weakened here.

Automatic Code Author, structural continuation, robustness/abandonment, external
research, the primary campaign UI/morning report, intelligence benchmarks and
overnight soak remain unfinished. Existing baseline/numeric campaigns continue to
work. No new frontend, strategy rule, engine, sandbox, dependency or schema was
introduced by this discovery continuation.

### Verification and manual developer check

Verified on 2026-10-11 against this continuation's final application/test tree:

- Focused discovery, campaign planning, memberships and Director suite:
  **76 passed** (20.51 seconds).
- Full backend with `LEDGER_TEST_DOCKER=1`: **1,138 passed, zero failures/errors/
  skips**, one existing Starlette/httpx warning, **449.98 seconds**. JUnit agrees.
- Included in that total: **12 new discovery tests**, **16 sandbox unit tests**,
  **18 real-Docker security/lifecycle tests**, **7 Docker research-loop tests**.
- Frontend: **128 passed**, zero failures/skips. Production build **passed**,
  confirmed separately with native exit code **0**.
- The first PowerShell verification wrapper terminated on redirected Vite stderr
  after the successful build (existing large-chunk advisory). The separate native
  build recheck passed; no application/test fix was needed. Do not interpret that
  wrapper exit as a backend or frontend test failure, or claim the wrapper itself
  returned success.
- Docker: **zero Ledger research containers** remain. All six unrelated stopped
  containers retain their original IDs/statuses. No pruning occurred.
- `git diff --check` passed. No frontend/browser changes were made; browser smoke
  was not repeated. No application/test edits followed the full backend run.

Artifacts: `C:/Users/jamie/Project/research-director-discovery-final/` contains
`verification.log`, `backend.xml`, `frontend-build.log`, the initial `frontend/`
and successfully rechecked `frontend-recheck/` build.
Current cumulative working tree: **13 modified tracked files, 11 new files**,
all uncommitted. This includes preserved checkpoint-1/2 changes, not just the
two new discovery files.

Create an ordinary FIND_STRATEGIES campaign with an explicit policy, then call
`POST /api/strategy-lab/research-campaigns/{id}/auto-prepare`. Adequate existing
US-equity intraday cache is required (default policy needs at least 565 observed
completed dates). Inspect `queue`, `plans` and `discovery.warnings`; provision
`/{id}/projects`, then authorize `/{id}/development` using the existing explicit
account/cost configuration. Closing the browser does not stop authorized execution.
An absent cache or insufficient history must return an error while retaining a
DRAFT campaign. Repeating successful preparation must return the same frozen plan.

New files: `backend/app/research_agent/discovery.py` and
`backend/tests/test_research_discovery.py`. Existing continuation files extended:
`campaigns.py`, `campaign_projects.py`, `api/research_campaigns.py`, and these two
status documents. All changes remain uncommitted; the prior checkpoint-2 working
tree was preserved.

## Autonomous Research Director: checkpoint 2 (2026-10-10)

**Current status: PARTIAL, backend baseline and numeric campaign execution works.**
This supersedes checkpoint 1's control-plane-only status below. It does not claim
minimal-prompt discovery, automatic code creation or 24-hour research acceptance.

### Shared datasets and project provisioning

`campaign_projects.provision` creates all prepared campaign projects and their
shared dataset memberships in one transaction. Project IDs and dataset IDs are
deterministic within the campaign. Retries return the same projects; deleted
records are not recreated. The additive `agent_dataset_memberships` table links
the existing `agent_projects` and `agent_datasets`; no parallel dataset registry
or performance store was introduced.

All families for a market/timeframe see exactly the same holdout record. Consuming
it changes its state for every member, including after restart. An outside project
cannot obtain access merely by naming that dataset. Provisioning rechecks saved-run
and registered-dataset exposure under the registration transaction, so a holdout
inspected after planning rejects registration and rolls back every new project.
Source and plan hashes are checked. Consumed validation cannot be supplied as
campaign hypothesis evidence or imported into campaign development analysis.
Candidate, regime and final validation verification use the same memberships.

Overlapping protected allocations across different timeframe plans or equivalent
futures aliases currently fail conservatively at registration; joint planning
across those overlapping scopes remains unfinished. No independent unseen copies
are created to make registration succeed.

### Director execution and budgets

`ResearchDirector` is owned by AppServices and wakes independently of the browser.
It reuses `workflow.start/observe`, BacktestJobs, ResearchLoop, the existing committee,
HypothesisRepository and Trials. It never imports generated code or changes engine
fills. The first phase queues a frozen baseline for each provisioned project,
inspects its saved result, optionally authorizes the requested bounded numeric
cycles, then proceeds to the next family/project.

Numeric progression is baseline -> Researcher -> Devil -> Manager -> immutable
preregistration -> unchanged control -> declared variants -> existing trade-level
feedback -> next authorized cycle/family. Duplicate-axis rejection remains in
ResearchLoop. A family failure stops that family's work and allows the queue to
continue. Completing this numeric phase is **not** candidate acceptance or evidence
that a strategy has an edge. Terminal campaign states explicitly distinguish
`BASELINES_COMPLETE` and `DEVELOPMENT_COMPLETE` from full research-product completion.

Account/risk/cost settings must be provided explicitly; start cannot silently move
the frozen strategy, symbol, timeframe or dates. Numeric execution requires model
summary consent, a configured/priced model, and the policy's parameter-research
allowance. The model/pricing identity is frozen. Conservative worst-case simulation,
hypothesis, model-call, monetary and compute allowances are reserved before dispatch;
project-level service limits are capped to the same allocation. Unused reservation
is not claimed as actual spend or silently recycled. This is deliberately
conservative, not yet an adaptive budget allocator.

The queue's normal progress checks also enforce campaign state and deadlines.
Campaign projects cannot use the ordinary baseline/loop endpoints to bypass
Director authorization. Locked holdout preauthorization remains a modeled policy
option, not an implemented automatic grant; validation remains an explicit
candidate-bound operation.

### Lifecycle and recovery

The Director uses the persisted baseline request key and existing queue recovery.
A restart after enqueue or saved completion reconciles that job/result instead of
creating another baseline. Pause revokes new work and cancels in-flight baseline
or loop work. Resume preserves the original wall deadline and reservations; it
continues remaining projects. Interrupted/failed/cancelled experiments are **not
silently rerun**. Stop-after-current lets the active baseline or current numeric experiment
finish before pausing; it does not start another committee review/cycle. Cancel does not remove immutable evidence.

The backend supervisor uses an event plus a five-second reconciliation interval;
no browser polling performs execution. Storage-supervisor failures back off and
stop after three attempts with a safe API-visible error category. Per-campaign
coordination failures pause that campaign. Model failures currently stop the
family without repeated paid retries. Event-driven completion wakeups and richer
provider Retry-After handling remain future work.

### Advanced API and manual developer acceptance

All routes are below `/api/strategy-lab/research-campaigns`:

1. `GET /policy` returns explicit defaults and QUICK/STANDARD/DEEP presets.
   `PUT /policy` updates defaults; existing campaign snapshots do not change.
2. `POST /` creates a request with `request_key`, `mode`, optional `prompt`,
   `strategy_key` where needed, and optional explicit `policy`.
3. `POST /{id}/prepare` accepts registered-strategy `entries` (family_id,
   strategy_key, reason) and completed-session `coverages` (symbol, timeframe,
   provider_namespace, source_fingerprint, completed_through, sessions).
   These manifests are **operator supplied**; automatic provider coverage discovery
   is not implemented and a supplied manifest is not independent proof of coverage.
4. `POST /{id}/projects` provisions shared datasets/projects and returns their IDs.
5. `POST /{id}/development` accepts `configurations` keyed by those project IDs,
   optional `numeric_cycles` (default zero), and acknowledgement exactly
   `Authorize frozen campaign development runs and configured model summaries`.
   Each configuration must explicitly supply starting_balance, risk_value,
   commission_per_order, spread_bps, slippage_bps and max_leverage. Additional normal
   BacktestRequest settings may be supplied. The fixed plan supplies identity/dates.
   Set policy `send_development_summaries` true and configure model/prices before
   requesting numeric cycles. Family limits and budget may reject an oversized run.
6. Close the client. Backend services continue the approved work. `GET /{id}` shows
   project progress, reserved budget, completed baseline/cycle counts, shared holdout
   consumption, audit events and supervisor health. `GET /` lists campaigns.
7. `POST /{id}/pause`, `/resume`, `/cancel` or `/stop_after_current` controls the
   campaign. Restart Ledger during execution to reconcile original queue identities.

These are advanced integration steps, **not the requested final minimal-input user
experience**. The simple Autonomous Research page and automatic queue/data selection
remain outstanding. No order placement, deployment or automatic promotion route exists.

### Remaining product work

- Automatic coverage adapter/discovery queue and minimal-prompt project setup.
- Automatic Code Author, conceptual decisions, quarantine/Docker continuation.
- Diagnostic-driven confluence iteration, automatic robustness/candidate freezing,
  substantive abandonment decisions and adaptive allocation across families.
- Optional external literature discovery with source/license provenance.
- Primary UI, concise morning report and candidate-diversity reporting.
- Synthetic research-intelligence benchmark, independent VWAP benchmark and
  compressed/overnight soak. Existing lifecycle tests are not a 24-hour soak claim.
- Campaign-generated child validation/promotion remains a separate explicit gate.

### Checkpoint 2 verification

Final verification against the checkpoint-2 application/test tree on 2026-10-10:

- `Verify-Ledger.ps1` with `LEDGER_TEST_DOCKER=1`: **1,126 backend tests passed,
  zero failures/errors/skips**, in **475.66 seconds**. JUnit independently records
  1,126 tests and zero failures/errors/skips.
- Included: **39 campaign/planning tests**, **8 shared-project/dataset tests**,
  **17 Director tests**, **16 sandbox unit tests**, **18 real-Docker
  security/lifecycle tests**, and **7 Docker research-loop tests**. These are
  subsets of the backend total, not additional tests.
- Final focused Director/ResearchLoop checks: **26 passed** before the full run.
- Frontend: **128 passed, zero failed/skipped**. Production Vite build **passed**
  (151 modules, 1.08 seconds).
- Advisories: one existing Starlette/httpx deprecation warning; the production
  JavaScript chunk remains above Vite's 500 kB advisory threshold.
- Final Docker inspection: **zero Ledger research containers**. The same six
  unrelated stopped containers remain present with their original IDs/statuses;
  no pruning or unrelated-container operations were performed.
- Browser acceptance was **not rerun** for this backend-only continuation. The
  earlier 1024/1440/1920 px foundation results remain historical evidence.
- Final `git diff --check` passed. No application/test changes followed the
  final run; only this verification record and the short handoff were updated.

Artifacts outside the repository:
`C:/Users/jamie/Project/research-director-checkpoint-2-final/verification.log`,
`backend.xml`, and `frontend/`. The earlier intermediate run is superseded by
this final run, which includes the stop-after-current numeric-loop regression.

Current continuation inventory against committed foundation `8d73ebe`:
**13 modified tracked files and 9 new files**, all uncommitted. The new files
include the four checkpoint-1 files plus the five checkpoint-2 files below.
No files were deleted and no dependency was added. Schema additions are lazy,
additive campaign/action/event tables and `agent_dataset_memberships`; existing
project/dataset/run records are preserved.

New checkpoint-2 files: `backend/app/research_agent/campaign_projects.py`,
`backend/app/research_agent/director.py`, `backend/app/api/research_campaigns.py`,
`backend/tests/test_campaign_projects.py`, `backend/tests/test_research_director.py`.
Modified integration files: API router; research repository/access/hypotheses/loop/
workflow/candidate_checks/decisions/regimes; BacktestJobs and AppServices; existing
campaigns.py and the two handoff documents. No frontend, strategy rule, Docker image
or sandbox restriction was changed. All Director continuation work remains uncommitted.

## Autonomous Research Director: checkpoint 1 (2026-10-10)

Continuation boundary: **`8d73ebe`**, committed 2026-10-10,
"Add Research Agent, Market Concepts and Docker-isolated strategy research".
The foundation below is now committed. This continuation has four new files and
two modified documents; it does not carry forward the old uncommitted inventory
as current Git status.

**Historical checkpoint 1 status: PARTIAL (superseded by checkpoint 2 above).** The existing
Research Agent and isolated execution remain operational. This checkpoint adds
backend policy, metadata-only dataset planning and a durable campaign control
plane. It intentionally does not expose an operational Start button, start a new
background worker, spend model budget or authorize generated-code execution.
The earlier final verification below belongs to the completed Docker foundation.

### Implemented policy and planning

`campaign_policy.py` defines a versioned strict policy and explicit presets.
STANDARD permits at most 1,440 wall-clock minutes, 240 simulations, 24 hypotheses,
12 children, six families, 60 model calls, USD 10 and 720 compute minutes. QUICK
sets 60 minutes / 24 simulations / three hypotheses / two children / two families /
12 calls / USD 2 / 45 compute minutes. DEEP sets 2,880 minutes / 600 simulations /
60 hypotheses / 30 children / ten families / 180 calls / USD 30 / 1,440 compute
minutes. These are ceilings, not promises of expenditure, runtime or profitability.
CUSTOM will use an explicit policy; no guessed currency conversion is performed.

Defaults select QQQ and 1m, both directions, minimum sample 30 and maximum
20-percent development drawdown. Costs require the existing instrument-aware
engine configuration; a zero-cost assumption is not manufactured. Code generation,
external research and model-summary consent default off. The future campaign UI
must clearly collect those permissions to enable code/model research. Holdout
consumption defaults to human approval. A preauthorization field is modeled but
**does not itself grant dataset access**. Strict schemas reject Docker arguments,
mounts, environment overrides and arbitrary actions. Global defaults are stored
in `app_settings`; each campaign snapshots its full policy. Changing defaults
cannot change an existing campaign or a retried creation request.

`dataset_planner.py` accepts a manifest of explicitly supplied completed sessions,
provider namespace and source fingerprint. It does not infer sessions from
weekdays, cache min/max timestamps or inspected results. Defaults reserve 250
warmup sessions, require at least 252 development and 63 holdout sessions, allocate
70 percent of post-warmup sessions to development subject to those minima, and
split development into three chronological internal windows. All date boundaries
and the manifest hash are frozen before performance inspection. Future OOS is
reported as unavailable rather than fabricated from historical dates.

The planner reads saved-run scope metadata and registered dataset metadata only.
Futures aliases share the existing contract-family exposure check. Protected
warmup/development overlap rejects planning. An exposed or already registered
holdout is explicitly `UNAVAILABLE`; the planner never slides boundaries to find
a convenient replacement or labels an inspected period unseen. Missing history
rejects the requested split. Unknown prior human exposure remains a limitation.
A proposed plan does not yet register data grants or prove provider completeness.
A provider/cache adapter that supplies validated session manifests remains needed.

### Durable campaign control plane

`campaigns.py` adds lazy, additive `agent_campaigns`, `agent_campaign_actions` and
`agent_campaign_events` tables. No existing schema/data is rewritten. Campaigns
support Find, Improve and Idea requests, immutable creation keys, registered-strategy
queue identities/source provenance, frozen coverage plans and event reports.
Each prepared campaign requires coverage for every policy symbol/timeframe.

The internal decision contract lists a bounded set of Director actions. Reservations
are atomic and idempotent, preserve one service request key across restarts, enforce
campaign ceilings/deadlines/authority and block overlapping unresolved actions.
The future dispatcher must derive estimates using trusted services, never accept
LLM arithmetic as authoritative, reconcile the original service key and settle the
result before admitting another action. Current pause/cancel/stop-after-current
control-plane gates reject subsequent reservations; they are **not yet integrated
with cancellation of running project jobs**. There is no public Start/Resume route
until those lifecycle services are connected. Persisting records alone is not an
unattended research implementation.

### Integration findings and remaining sequence

1. **DONE:** versioned policies, deterministic session planner, persistent campaign
   records, action identities, reservation/authority guards and focused tests.
2. **NOT IMPLEMENTED:** session-coverage provider adapter, automatic discovery queue,
   project attachment and safe shared campaign holdout ownership. Existing dataset
   grants are project-owned; repeated per-project registration must not create fake
   independent holdouts or bypass the global firewall.
3. **NOT IMPLEMENTED:** Director dispatcher and restart/pause/resume/retry orchestration
   using existing BacktestJobs/ResearchLoop. BacktestJobs currently recovers saved
   results and otherwise requires an explicit retry; the Director must reconcile
   that evidence before authorizing a new attempt. It must not enqueue duplicates.
4. **NOT IMPLEMENTED:** Code Author and structural decision service. Existing
   quarantine requires a frozen candidate and a bounded draft count, and the
   current committee contract proposes numerical axes only. These are integration
   points to extend carefully, not reasons to bypass quarantine, parity or Docker.
5. **PARTIAL:** diagnostics, cost/regime/simplification and validation already exist,
   but automatic selection, abandonment, confluence iteration and candidate-driven
   campaign allocation are not wired. Finite prefix checks remain finite tests.
6. **NOT IMPLEMENTED:** external literature discovery, source/license records,
   campaign-level diversity reporting, morning report, simple primary UI and
   exceptional notifications. Existing manual/audit UI is preserved.
7. **NOT IMPLEMENTED:** end-to-end autonomous synthetic benchmark, independent VWAP
   reasoning benchmark and compressed/real overnight soak. No 24-hour autonomy
   claim is made from campaign CRUD tests.
8. **REQUIRES EXTERNAL PROVIDER:** live LLM reasoning/code authorship, historical data
   access and optional literature search. No real credential was read or provider
   request made by this checkpoint.
9. **REQUIRES USER DEPLOYMENT DECISION:** all future paper/live deployment and capital
   actions. None is added or authorized by this work.

### Checkpoint verification and developer acceptance

Full checkpoint verification passed on 2026-10-10:

- **1,101 backend tests passed**, zero failures/errors/skips, 449.77 seconds.
- This includes **39 new campaign/planning tests**, **16 sandbox unit/protocol
  tests**, **18 real Docker security/lifecycle tests**, and **7 Docker research-loop
  integration tests**. These are subsets of the backend total, not extra tests.
- **128 frontend tests passed**, zero failures/skips.
- **Production frontend build passed**, 151 modules, 1.39 seconds; identical
  application asset identities to the committed foundation.
- `git diff --check` passed for this continuation. Documentation links passed.
- Final Docker listing: zero Ledger research containers; the same six unrelated
  stopped containers remain. No unrelated Docker resources were operated on.
- Existing Starlette/httpx deprecation and frontend bundle-size warnings remain.
- Browser acceptance was not rerun: no frontend or runtime wiring changed. The
  prior foundation's three-viewport results are historical evidence, not new
  autonomous UI acceptance.

Command: `Verify-Ledger.ps1` with `LEDGER_TEST_DOCKER=1` and output directory
`C:/Users/jamie/Project/research-director-checkpoint-1`. Exact log and JUnit counts
are in that directory's `verification.log` and `backend.xml`; production assets
are under `frontend/`. No application/test changes followed this full run.

New files: `backend/app/research_agent/campaign_policy.py`,
`backend/app/research_agent/dataset_planner.py`,
`backend/app/research_agent/campaigns.py`, and
`backend/tests/test_research_campaigns.py`. The only other checkpoint changes are
this major update and the short handoff. Existing application wiring, UI, models,
strategies, engine, provider paths and Docker image are unchanged.

Run focused tests from `backend` with
`.venv/Scripts/python.exe -B -m pytest tests/test_research_campaigns.py -q`
(using an isolated writable `--basetemp` if the default Windows temp directory
is restricted). The tests use synthetic sessions and temporary SQLite databases;
they make no external requests. The first local attempt hit Windows temp-directory
permissions; rerunning with a workspace-owned temporary directory passed.

There is no user-facing autonomous campaign to start yet. Continue using the
existing Research Agent workflow below. Do not treat a prepared campaign record or
its proposed holdout as executed research or a consumed validation grant.

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

### Docker foundation verification: 2026-10-10

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

At foundation verification, these changes were uncommitted, including staged/user strategy work.
They were subsequently committed as `8d73ebe`; see the Director section for current changes.
The inventory below lists every changed/new application, test and documentation
file relative to `afb73e9`: 53 modified files, 114 new files, no deletions at the foundation verification boundary.
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
