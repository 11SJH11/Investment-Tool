# Research Agent current status / handoff

## Current phase — verified 14 October 2026

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
Next unresolved integration: autonomous structural candidate freeze/validation,
simplification/regime orchestration and final family disposition, followed by
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
