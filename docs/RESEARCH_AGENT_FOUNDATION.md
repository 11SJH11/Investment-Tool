# Research Agent current status / handoff

## Current: structural Docker repair (21 October)

See the [major update, Docker repair appendix](RESEARCH_AGENT_MAJOR_UPDATE_2026-10.md#21-october-structural-docker-execution-repair)
for diagnosis, exact image identity, isolation, verification and use instructions.
Tag resolution failed on the healthy Docker Desktop daemon, and the installed
image was stale. Exact verified immutable-ID resolution and an allowlisted rebuild
restore execution without weakening isolation. Structural launch now probes the
actual worker; campaign and sandbox views expose persisted execution timelines.
The final combined real-Docker suite passed **59 tests**; frontend **139 passed**;
documented isolated production build passed, with the existing chunk-size warning.
Final full backend: **1,773 passed, 41 skipped** (588.16s); diff check passed.
No Ledger research containers remain; six unrelated stopped containers remain.
No paid model call, user campaign mutation, live order or account switch occurred.
Restart Ledger normally when no campaign is active to load the backend changes.

The [unified development handoff](UNIFIED_DEVELOPMENT_2026-10.md) is authoritative
for the ongoing MT5/deployment, screenshot and Algo Trading roadmap. MT5 demo
clock evidence is saved, but the server's DST transition rule is unconfirmed;
automated execution remains disabled. This repair does not complete that roadmap.

## Previous: session replay and timing closeout (17 October)

Completed-session parity is now available in Forward Validation. It creates fresh
strategy/engine instances, replays the immutable prefix through the provider close,
and compares cumulative setup/trade hashes, final engine state and marked equity.
PASS/FAIL results persist; source drift, incomplete sessions and unavailable bars
cannot pass. Live strategy instances/checkpoints are not changed.

Paper comparison now exposes broker submission minus decision and broker completed
fill minus submission delays when those timestamps exist; negative/missing values
remain unknown. This is not individual-fill latency. The metrics panel shows the
last persisted pending signal, with an explicit limitation for signals that never
appeared in pending snapshots.

Frontend: 136 tests passed; production build passed (164 modules, existing chunk
warning). Focused parity/comparison/service/Journal checks: 20 passed. Mocked
Forward Validation and parity controls passed at 1024/1440/1920. Final full backend:
**1,459 passed, 38 skipped**, one existing Starlette warning, 518.43s. Diff check
passed. No Ledger research containers remain; six unrelated stopped containers
were untouched. The isolated browser/Vite processes were stopped.

External acceptance still requires the user's configured feed/account, adequate
IEX history and explicit paper arming during a provider session. No real orders or
paid model calls were made. This does not certify real trading reliability or
research quality. See the phase ledger's manual checklist and limitations.
The later MT5/results phase has not started.

## Previous increment: forward shadow metrics (17 October)

Forward Validation now includes a per-deployment performance table: closed N,
wins/losses/breakeven, win rate, P&L PF, R sample/average/total, marked return and
drawdown, directional PF, average/largest winners/losers and session-close winners.
Observed sessions use New York checkpoint dates, not elapsed calendar days.
All trades are included before display truncation; accounts are never pooled.
Undefined ratios remain unavailable. N < 30 is a visible descriptive low-sample
flag, not a confidence test. Results cache by deployment revision.

145 paper/forward/broker backend checks and 136 frontend tests passed. Production
build passed (162 modules). Mocked forward/metrics browser checks passed at
1024/1440/1920. Full backend not rerun this increment. No orders/model calls.

Remaining: session replay/parity workflow, explicit last-signal presentation,
latency evidence, operational acceptance and opt-in provider/model checks.

## Previous increment: exact B shadow/paper comparison (17 October)

Forward Validation now compares closed B Journal trades using exact recorded
entry decisions, experiment, frozen definition, symbol and direction. Shadow
pending-market-order and paper decision checksums are verified. Missing evidence,
duplicate candidates and missing closed counterparts are explicit; no approximate
timestamp pairing or mutation of Journal facts/reviews occurs.

The panel exposes both Journal IDs, adverse entry/exit slippage per share, P&L
difference only where known, and duration difference only with broker-completed
fill timestamps. Individual-fill/submission latency remains unavailable.

142 paper/forward/broker backend tests and 136 frontend tests passed. Production
build passed (161 modules; existing chunk warning). Mocked Forward Validation and
comparison browser checks passed at 1024/1440/1920. Full backend was not rerun this
increment; prior full-suite counts below belong to their recorded trees.

Remaining: complete forward metrics, session replay/parity workflow, latency
instrumentation, operational risk acceptance and opt-in provider/model checks.

## Previous increment: reconciled paper Journal import (17 October)

The backend paper monitor now imports closed reconciled positions through the
existing canonical broker execution/repository path. Pending cumulative fills are
not published as closed trades. Canceled partial entries and weighted partial
exits are supported; stable deployment/account/order identities prevent duplicates.
Reviews remain editable and execution facts remain read-only. Source label:
Alpaca automatic paper. No real orders were submitted.

Fees, net P&L and R remain unknown when order history lacks attributable cost/P&L
evidence. Observation timestamps are labelled and never presented as exact fills.
Ambiguous chronology fails without replacing Journal data. No new database schema.

35 focused backend checks and 136 broader paper/forward/broker checks passed;
136 frontend tests passed; production build
passed (160 modules). The previous full backend count of 1,439 passed/38 skipped
predates this increment; it is not a current-tree full-suite claim.

Still remaining: exact B shadow/paper matching, forward metrics, session parity,
operational acceptance and opt-in provider/model checks. Existing checkpoint
pending-entry evidence was inspected for exact matching; no approximate timestamp
matching was added. See the phase ledger for regression results.

## Previous increment: automatic shadow Journal linkage (16 October)

Closed Baseline/B/C/D simulated trades now enter Journal automatically with stable
per-deployment identities, frozen execution/source evidence and read-only facts.
Repeat projection preserves reviews and attachments. A preserving Journal source
constraint migration is covered by repeated-initialization and data tests.

33 focused backend tests and 136 frontend tests passed; production build passed.
Mocked Forward Validation and shadow trade details passed at 1024/1440/1920.
Final full backend: **1,439 passed, 38 skipped**, one existing warning, 510.89s.
`git diff --check` passed. See the
[phase ledger](RESEARCH_FORWARD_RESPONSIVENESS_2026-10-13.md) for commands and evidence.

Still unfinished: paper Journal reconstruction, exact B shadow/paper matching,
forward metrics/session parity, operational acceptance and opt-in real provider/
model checks. The next MT5/results phase remains gated.

## Previous increment: connected paper controls (16 October)

The user approved post-fill protection gaps for paper only. Backend monitoring,
explicit consent/arming, native MOC confirmation, partial-fill cancellation and
cancel-before-exit are connected to Forward Validation. No real orders were placed.
The approval gate below is historical and resolved; do not ask again.

Verification: **1,436 backend passed, 38 skipped** (492.81s); **44 focused tests
passed**; **136 frontend tests passed**; production build passed (160 modules).
Mocked browser controls passed at 1024/1440/1920. Prior Docker verification:
29 passed on unchanged sandbox code. See the
[phase ledger](RESEARCH_FORWARD_RESPONSIVENESS_2026-10-13.md) for restrictions.

Remaining: Journal linkage, forward metrics/session parity, operational risk
acceptance and opt-in real-provider/model checks. The current phase is incomplete.
The newer MT5/results phase remains gated.

## Historical: independent paper decisions and protection gate (16 October)

`c543237` committed the IEX shadow runtime/UI and initial paper boundary. Subsequent
work adds a separate broker-position-driven B evaluator, replayable decision
observations, durable dispatch reservations, restart/process fencing, explicit
cancel/flatten primitives and native closing-auction requests. Paper remains
disconnected from application activation: no orders have been placed.

The user requires broker-managed session-close protection. Alpaca documents MOC
orders for existing positions but no atomic entry-plus-MOC combination. The tested
post-fill primitive cannot eliminate the fill-to-protection interval or the gap
during cancellation/replacement. **Coordinator arming fails closed.** A further
decision is pending: keep automatic paper disabled, or explicitly accept those
intervals for paper-only post-fill protection. Do not silently fall back to a
Ledger-owned pre-close timer. See the phase ledger for evidence and acceptance.

The current phase is NOT COMPLETE; the attached MT5/results phase has not started.
Remaining work includes approved protection lifecycle, operational paper controls,
Journal linkage, forward metrics/parity UI and real-provider acceptance.

Final-tree verification for this increment: **1,429 backend passed, 38 skipped**
(520.97s; existing Starlette warning); **34 focused paper tests passed** (15.39s).
Separately, **29 real Docker security/lifecycle/research-loop tests passed**
(165.65s). No Ledger containers remain; the same six unrelated stopped containers
were untouched. Frontend remains **136 passed**, production build passed, mocked
browser acceptance passed at 1024/1440/1920. No real broker/model calls or orders.

## Current increment — IEX shadows and paper safety foundation (16 October)

Four independent frozen shadows now have a completed-bar log, incremental engine,
replay-verified recovery, backend-owned IEX preparation/polling and Forward Validation
UI. User selected IEX for warmup and incoming data. Missing/revised minutes halt;
strict 60-session warmup can fail on sparse IEX history. No real-feed acceptance
has been performed. Paper transport/risk-intent reconciliation is tested but is
NOT connected to an automatic executor or UI arming. No orders were submitted.

125 focused backend tests passed (42.30s); 136 frontend tests passed; production
build passed (159 modules; existing bundle warning). Mocked browser smoke passed
1024/1440/1920: preparation consent, four states, halt, no overflow/runtime errors.
Full backend/current-phase acceptance remains outstanding. See the
[phase ledger](RESEARCH_FORWARD_RESPONSIVENESS_2026-10-13.md) for exact checks,
schema additions and unfinished work. Previous entries below are historical.

## Forward foundation — 16 October 2026

Checkpoint 8 is in progress. Added atomic, idempotent persistence for four
independent inactive Baseline/B/C/D shadow deployment definitions, pinning the
actual loaded strategy archives, frozen D6 parameters and explicit account costs.
No strategy rules changed. No activation, provider ingestion, runtime evaluation,
paper orders or FUTURE_OOS claims yet. User source/output files remain untouched.

**35 focused tests passed** (8.22s, zero skips), covering deployment persistence,
existing source archives and registry refresh, including the actual four locally
installed contracts. No frontend changes; no full-suite/build rerun this increment.
Additive on-use `forward_experiments` / `forward_deployments` tables use existing
source archives. See the [phase ledger](RESEARCH_FORWARD_RESPONSIVENESS_2026-10-13.md)
for exact scope and the next runtime/parity work. The broader phase is unfinished.

## Latest checkpoint — 16 October 2026

Declared generated-strategy development regimes are implemented and verified.
Optional named periods, definitions and sources are frozen before execution,
bounded to development dates, budgeted up front and run through the existing
Docker control/child/prefix checks at original and doubled costs. Reports keep
regime results separate; missing/adverse evidence blocks promotion. Labels remain
user assumptions, not verified classifications. No schema migration or trading
behaviour changes. Existing campaigns default to no declared regimes.

Verification: **163 focused backend tests passed**, including six real-Docker
campaign scenarios (288.19s); **75 compatibility tests passed / one opt-in skip**;
two additional authority tests passed. These sets overlap. **136 frontend tests
passed**, production build passed, browser smoke passed at 1024/1440/1920.
No research containers remain; six unrelated stopped containers unchanged.
Full backend suite was not rerun. See the
[current phase ledger](RESEARCH_FORWARD_RESPONSIVENESS_2026-10-13.md) for exact
commands/suites, limitations and files.

Remaining: broader real-model/lifecycle acceptance, independent forward shadows,
paper-only B execution with risk/reconciliation, Journal/Forward Validation
integration and final phase-wide verification. No paper/live orders enabled.

## Current phase — verified 15 October 2026

Latest verification: two distinct generated children now have real-Docker
acceptance across a coordinator restart between completed attempts. The second
author receives prior evidence; reservations remain fixed; simplification rejects
the neutral second child and the family closes without consuming the holdout.
Repeated ticks do not repeat models/jobs. **14 structural campaign tests passed**
(210.64s; five real-Docker scenarios). Application/frontend code is unchanged;
the previous 207-test focused run, 135 frontend tests, build and browser results
were not rerun. Only the test and handoff docs changed. This does not establish
live-model quality, regime orchestration or forward/paper readiness. See the
[current phase ledger](RESEARCH_FORWARD_RESPONSIVENESS_2026-10-13.md).

Previous increment: completed families now have durable development closeouts:
baseline-only, review needed, frozen pending validation, abandoned development,
inconclusive, execution blocked or stopped without conclusion. Entry/policy hashes
are checked before display. Restarts preserve the same record and do not repeat
paid work. These records grant no acceptance/deployment authority and do not
rewrite historical campaigns. **207 focused backend tests passed** (199.02s,
four real-Docker campaign paths), **135 frontend tests passed**, production build
and browser checks at 1024/1440/1920 passed. No migration. Full backend suite not
rerun. Exact scope, environment retries and remaining work are recorded in the
[current phase ledger](RESEARCH_FORWARD_RESPONSIVENESS_2026-10-13.md).

Previous increment: new campaigns automatically assess removal of the single
generated feature using existing Docker parent-parity controls over the full
development period and original/doubled-cost windows. No observed expectancy gain
in any paired check means retain the simpler parent, not freeze the child.
Incomplete evidence blocks promotion; existing gates still apply. Historical
policies keep their original behavior. No extra simulations, schema migration or
holdout exposure. This is not arbitrary parent-rule simplification or statistical
significance. **194 distinct focused backend tests passed** (138 + 56, including
four real-Docker campaign cases), **135 frontend tests passed**, build and browser
smoke at 1024/1440/1920 passed. No Ledger research containers remain. Full backend
suite not rerun. See the [current phase ledger](RESEARCH_FORWARD_RESPONSIVENESS_2026-10-13.md)
for exact test commands, initial Docker image issue and remaining work.

Previous increment: structural hypotheses are now hashed and persisted before code
generation. Numeric and structural research history is unified in the campaign
report and next author's development context, preserving challenges, failed /
interrupted attempts, source identities and observed research exposure. Unknown or
validation-derived evidence scopes are redacted; failed integrity checks block
further author spending. The UI has an expandable hypotheses/research-debt view.
No new migration or execution authority. **50 focused backend tests passed**
(140.95s, including four real Docker acceptance cases), **135 frontend tests passed**,
production build and browser checks at 1024/1440/1920 passed. Full backend suite
not rerun. See [current phase ledger](RESEARCH_FORWARD_RESPONSIVENESS_2026-10-13.md)
for exact files, evidence and limitations. Autonomous simplification/regime
orchestration, complete campaign acceptance, forward shadows and paper execution
remain unfinished; descriptive debt counts are not a statistical correction.

Previous increment: new structural campaigns can explicitly authorize automatic
validation of one frozen generated candidate. Selection and criteria are durable;
only one qualifying candidate and one untouched matching dataset are allowed.
Ambiguity, changed policy, expired/budget-exhausted authority or dispatch failure
stops for review. Restarts reconcile the same grant without retrying interrupted
execution. Legacy executions gain no automatic authority. The campaign form shows
explicit holdout consent; progress and cancellation stay available after development.
**123 focused backend tests passed** (189.79s, including real Docker), **135 frontend
tests passed**, production build and browser checks at 1024/1440/1920 passed.
No migration or research-container leftovers. Full backend suite not rerun.

Previous increment: generated candidates now use the existing final research decision
workflow. Acceptance rechecks the freeze/approval audit identities, archived source,
Docker image, dataset/configuration, control/prefix evidence, result hashes,
recomputed comparison and fixed validation criteria. A structured review and
explicit acknowledgement remain required. Decisions are immutable and grant no
registration, deployment or trading authority. Rejection needs no holdout exposure.
The shared decision UI hides incompatible numeric research controls for generated
candidates. **76 focused backend tests passed** (151.14s, real Docker enabled),
**133 frontend tests passed**, production build passed, and mocked browser checks
passed at 1024/1440/1920. No research containers remain; no schema migration.
The complete backend suite was not rerun for this increment. Detailed evidence and
remaining work are in the linked current-phase checklist below.

Previous increment: explicitly approved validation of frozen generated candidates
now uses the existing Docker runner and dataset-grant store. Source, image,
criteria, data bounds and simulation budgets are checked before dispatch. The
ordinary host job queue rejects generated validation. Cancellation/restart retain
dataset exposure without automatic retries. Candidate details offer separate
isolated approval, polling and cancellation controls. No schema migration.
Final focused backend verification: **137 passed** with real Docker enabled
(235.21s); **133 frontend tests and production build passed**, as did mocked
browser acceptance at 1024/1440/1920. The 1,256-test
full-suite result below predates this increment and candidate freezing.

The current [research / forward validation / responsiveness audit and checklist](RESEARCH_FORWARD_RESPONSIVENESS_2026-10-13.md)
starts at `8754cff`. Initial audit and the configuration-only Use settings fix
are complete and verified. Measured progressive Run Viewer loading and causal
Docker delta transport are committed. Full-period evaluation with historical
warmup, complete development-window cost checks and larger archived dependencies
passed 1,256 backend tests with Docker enabled, 133 frontend tests, the production
build and three-viewport browser regression. Heavy Analysis and delayed-response
acceptance passed; no Ledger research containers remained.
Full autonomous acceptance and shadow/paper execution remain open. Paper execution
remains disabled. Detailed measurements and limits are in the linked checklist.
The older full-suite results below refer to previous increments.

Latest implementation commits: `f9ce0c1` (full-period/warmup), `37dfcf5` (archived
dependencies/spending), `e0b5709` (complete development-window cost checks),
`e5ffdde` (heavy Analysis and response-race acceptance). No schema migration.
Next unresolved integration: generated simplification/regime orchestration,
automatic final family disposition and coherent hypothesis/research-debt integration, followed by
independent forward shadows, paper-only execution, reconciliation and Journal UI.
Do not describe the full Research Agent or requested forward phase as complete.

## Current continuation — 12 October 2026

Starting tree: `01ce536` (Agent foundations), including the user's local confluence
strategies. Archived parent/dependency selection, container-only dependency loading,
bounded structural iteration (one by default, at most three), duplicate-source
suppression and deterministic development triage are implemented. The campaign UI
now exposes the attempt limit and triage reasons. These are development checks,
not automatic acceptance or holdout authority. No new database migration.

The additional [performance audit](BACKTEST_PERFORMANCE_AUDIT_2026-10-12.md) is in
progress. Four bounded profiles identified repeated session normalization as the
dominant initial cost. One exact-parity normalization optimization is implemented;
complete three-month cache comparisons show 15.3–18.0% lower wall time with exact
result parity across D6, MSS15, MidVol and SweepS5.

Final verification completed **13 October 2026**: **1,234 backend passed**, zero
failures/errors/skips, **563.80 seconds**, including **31 real-Docker tests**.
**133 frontend tests passed**; production build passed. Browser fixtures passed at
1024/1440/1920px, including attempt limits and development-verdict reasons, with
no runtime errors or page overflow. `git diff --check` and document links pass.
Zero Ledger research containers remain; six unrelated stopped containers are
unchanged. The isolated browser/server are stopped. Existing Starlette/httpx and
frontend bundle-size advisories remain. Earlier counts below are historical.

The first full run had 1,233 passes and one Docker image-tag lookup failure.
Restoring the tag to its same verified immutable image repaired the environment;
the isolated regression and complete rerun passed without application changes.
Artifacts: `C:/Users/jamie/Project/director-audit-20261012/`, final backend log/XML,
frontend test log/build and browser screenshots. No live model/provider calls.

Still required: full-period generated-child execution with sufficient warmup,
complete robustness/acceptance/abandonment workflow, novel-idea/literature synthesis,
intelligence benchmarks and overnight/live-provider/model acceptance. The sandbox
still permits only 10,000 aggregate bars and bounded samples. A long-warmup strategy
can produce no qualifying trades in these samples; passing control parity alone
does not make that evidence sufficient. Archived dependencies remain bounded to
50 KB/32 modules; larger confluence inheritance chains fail closed.

The performance audit also still needs long-range/scaling measurements and progress
UX improvements. Do not mark checkpoints 3–6 or the complete audit finished.

The authoritative full update is [Research Agent major update - October 2026](RESEARCH_AGENT_MAJOR_UPDATE_2026-10.md).
It consolidates the work since committed boundary `afb73e9` (2026-10-05), including
Market Concepts, research workflows, storage, UI, provider integration and Docker.

Docker foundation verification (2026-10-10): **1,062 backend tests passed**, including
**18 real-Docker security/lifecycle tests** and **7 Docker research-loop tests**;
**128 frontend tests passed**; production build passed. Browser acceptance passed
at 1024/1440/1920 px. Final Docker inspection found zero Ledger research containers;
unrelated stopped containers remain untouched. No application/test edits followed
verification. The foundation is committed as `8d73ebe`; see the full update for its historical
inventory and verification advisories.

Latest continuation (2026-10-11): **checkpoints 3-6 remain partially complete**.
The full major-update document linked above now contains the current architecture,
per-checkpoint status, schema details, limitations and manual acceptance steps.

Implemented since the previous cache-discovery handoff:

- Bounded provider preparation with durable retries/recovery and fetch-level
  holdout/provider/range guards; US-equity intraday scope.
- Durable single-launch campaigns and separate first-session control references.
- Researcher / Devil / Manager / Code Author, shared paid-call reservations,
  archived-source consent, inert quarantine and automatic Docker dispatch.
- Exact control parity and bounded prefix checks remain mandatory. No generated
  source runs in the host process; sandbox limits and engine rules are unchanged.
- Campaign launch/status/report UI, with Advanced projects still available.
- Deterministic sample-size and winner-retention reporting without ranking,
  automatic acceptance, holdout consumption or deployment.
- Bounded samples fixed from each internal development window before dispatch,
  with real normal/2x engine-cost reruns, control parity and prefix checks per
  sample. Budget reservations cover all runs. The report has a separate sample
  table and warns when configured zero costs provide no stress.

Final verification: **1,206 backend tests passed**, zero failures/errors/skips
(560.60 seconds), including **30 real-Docker tests**: 18 security/lifecycle,
9 loop and 3 reference/author/campaign integrations. **132 frontend
tests passed**; production build passed (native exit 0, existing chunk advisory).
Browser fixture checks passed at **1024 / 1440 / 1920px**, including launch,
pause/resume, report, expanded robustness table and Advanced projects navigation, with no runtime errors or
page overflow. `git diff --check`, changed/new source whitespace and handoff
relative-link checks passed.

Final Docker inspection: **zero Ledger research containers**; the same six
unrelated stopped containers are untouched. Isolated browser/server stopped.
Initial targeted Docker preflight failed to resolve a listed tag. Reapplying the
tag to its same existing immutable image fixed lookup; the complete run passed
without changing Docker restrictions. One existing Starlette/httpx
warning remains. No live provider or paid model was called. Exact test breakdown,
commands, artifacts and the initial failure are recorded in the major update.

Still required: full-period robustness for generated children,
structural iteration beyond the first bounded child, archived dependency assembly,
autonomous acceptance/abandonment, novel-idea/literature synthesis, intelligence
benchmarks and overnight/live-provider/model acceptance. **Passing bounded Docker
samples does not complete checkpoints 4-6 or demonstrate a profitable strategy.**

All continuation changes are uncommitted (22 tracked modifications, 29 new files;
no deletions). This robustness increment requires no new schema migration.
Default structural research now reserves 30 simulations per family plus numeric
cycles, so use a sufficient budget (STANDARD rather than QUICK).
No frozen strategy, engine accounting,
Replay, Journal identity or broker execution behavior was intentionally changed.

The older checkpoint sections below are historical, not current completion claims.

Autonomous Director checkpoint 2 (2026-10-10): **complete within its stated scope**.
Continuation starts from committed foundation `8d73ebe`.

Completed: versioned policies, deterministic dataset plans, atomic shared-dataset
project provisioning, browser-independent baseline and bounded numeric research
execution through existing BacktestJobs/ResearchLoop, campaign budgets/deadlines,
pause/resume/cancel/stop-after-current, durable job reconciliation and an advanced
campaign API. Shared holdout records cannot be consumed independently per family.

Final checkpoint-2 verification: **1,126 backend tests passed, zero failed or
skipped** (475.66 seconds), including **18 real-Docker security/lifecycle tests**
and **7 Docker research-loop tests**. **128 frontend tests passed**; production
build passed. Docker inspection found zero Ledger research containers and the
same six unrelated stopped containers. Browser acceptance was not repeated:
this continuation changes no frontend code. Full results and advisories are in
the major update below. Application/test code was unchanged after this run.

Still unfinished: provider-backed complete coverage/novel-idea discovery, Code Author and structural
iteration, autonomous robustness/abandonment, literature discovery, primary UI and
morning report, intelligence benchmarks and overnight soak. There is no minimal-
prompt Find strategies workflow yet. Numeric/model failures stop that family safely;
interrupted experiments are not silently retried. No generated code executes on
the host, and no deployment/order authority is added.

See the major update's checkpoint 2 section for exact API steps, limitations and
integration files. Historical checkpoint 1 verification was 1,101 backend / 128
frontend passing; the current checkpoint results above supersede it.

Current foundation state (2026-10-10):

- Deterministic development research, bounded optional committee/loop, candidate
  checks, explicit validation and research decisions are implemented.
- Source archives, reproducibility manifests and evidence retention are implemented.
- Generated source stays quarantined; explicitly approved checks run only in offline
  Docker, using completed snapshots and the trusted host engine for accounting.
- Independent host guardian, cancellation, owned-container cleanup and restart
  reconciliation are implemented. Docker failure has no main-process fallback.
- Candidate UI exposes consent, progress, cancellation, parity and provenance.

See the major update for final verification counts, image identity, exact files,
security tests, limitations and step-by-step acceptance instructions.

Operational prerequisites: Linux/amd64 Docker with cgroups v2 and seccomp, one
Ledger backend per database, and an operator-built current sandbox image. Run
`backend/.venv/Scripts/python.exe -B backend/tools/build_research_sandbox.py`
from the repository root. No credentials or repository mounts enter the image.

Limits: one symbol / 10,000 aggregate bars / bounded deadline, explicit draft
approval, finite prefix testing, no generated-child automatic activation or
holdout grant. Live LLM/provider acceptance and complete data/image archival remain
external/operator responsibilities. Existing trusted Python strategy refresh is
a separate workflow and must not be used to execute unreviewed generated code.
