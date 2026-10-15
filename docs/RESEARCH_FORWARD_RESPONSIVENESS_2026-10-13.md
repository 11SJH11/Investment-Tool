# Research, forward validation and responsiveness: current phase

Audit boundary: `8754cff`, 13 October 2026. This is an implementation and
acceptance ledger, not a completion claim. The untracked local confluence modules
and research outputs belong to the user and are preserved. No credentials read.

## Continuation: structural hypotheses and development search debt (15 October)

Structural author requests now persist a hashed hypothesis before Code Author is
called: proposal, parent identity, evidence identity and discovery dataset IDs.
The existing `agent_reviews` document stores this additive field; there is no new
table or migration. Completed records remain protected by the existing terminal
review write guard. Old records are explicitly labelled reconstructed, not
retroactively claimed as preregistered. A mismatched hypothesis hash or identity
blocks further code-author spending.

`research_ledger.py` projects structural requests and numeric preregistrations into
one development history per linked family. It preserves rejected, failed and
interrupted requests, challenges, Manager reasoning and source/draft identities.
Campaign reports link these to saved structural outcomes and sandbox IDs. The next
author receives the bounded history alongside existing development evidence and
attempt results; it does not receive validation results or generated source from
old reviews. Records whose discovery datasets cannot be verified as development /
inspected development have their proposal and challenge text withheld. Reads do
not create new inspections or repeat paid work.

The campaign UI exposes an expandable hypotheses/research-debt section. Counts
distinguish requests, drafts, failures, pre-execution rejections, numeric hypotheses
and planned variants. They are descriptive exposure counts, **not independent
trials, a multiple-testing correction, or a profitability score**. Old failed
attempts cannot disappear merely because the process restarts. This does not yet
implement cross-campaign semantic idea deduplication or autonomous simplification /
regime tests; those remain separate orchestration work.

New files: `backend/app/research_agent/research_ledger.py`,
`backend/tests/test_research_ledger.py`,
`frontend/src/features/strategy-lab/ResearchSearchHistory.jsx`.
Integration changes: `author.py`, `campaign_report.py`,
`test_campaign_structural.py`, `AutonomousResearch.jsx`, browser
`campaign-smoke.mjs`, this ledger and the short Research Agent handoff.

Final verification: **50 focused backend tests passed**, zero failures/skips,
140.95 seconds, with `LEDGER_TEST_DOCKER=1`: `test_research_ledger.py` (8 new
tests), `test_research_author.py`, `test_campaign_report.py`,
`test_campaign_structural.py`, `test_campaign_validation.py`. Includes four real
Docker author/campaign acceptance cases. The initial test failures were new test
fixture assumptions (pre-existing numeric hypotheses, terminal review mutation
guard, and the mock sandbox's absent persistent table); corrected without
weakening production safeguards. Final log:
`C:/Users/jamie/Project/ledger-history-backend-final-20261015.log`.

**135 frontend tests passed**, zero failures/skips; production build passed
(156 modules, 963.18 kB JS, existing bundle-size advisory). A transient Windows
access error in unchanged files cleared on an identical build rerun after the
isolated smoke server stopped. Browser fixture acceptance passed at **1024 / 1440 /
1920px**, including expanded hypothesis/challenge/failure history, existing
campaign controls and validation cancellation; no runtime errors or page overflow.
Browser/server stopped. `git diff --check` passed. No live provider or paid model
was called. No full-backend completion claim is made for this incremental change.

## Initial audit at the 13 October boundary

This table records the starting gaps. Completed increments and current verification
are recorded below; it is not a description of the final current tree.

| Area | Status | Concrete implementation and remaining work |
| --- | --- | --- |
| Dataset governance | Implemented foundation; integration partial | `research_agent/repository.py`, `access.py`, `validation.py` persist protected datasets and enforce access. Validation exposure is called `INSPECTED_VALIDATION`; it must never become unseen again. Full autonomous lifecycle needs to use these guards. |
| Campaigns and budgets | Implemented foundation | `campaigns.py`, `campaign_policy.py`, `director.py`: durable policies, deadlines, reservations, Quick/Standard/Deep. A large budget does not imply that every requested research action is orchestrated. |
| Hypothesis ledger | Partial | `HypothesisRepository.register` freezes rationale, expected result, falsification, discovery datasets and committee reasoning with an idempotent request key. Its numeric axes contract is not the complete ledger for structural hypotheses and family search debt. |
| Committee | Implemented services; orchestration partial | Researcher/Devil/Manager/Code Author and cost reservations exist. `manager.choose` recommends cost/regime/simplification/validation actions; recommendations are not execution. |
| Iteration | Partial, not missing | `structural.advance` permits bounded distinct retries after completed insufficient/rejected evidence. Default one, cap three. It terminates at `REQUIRES_VALIDATION` or `STOPPED_WITHOUT_ACCEPTANCE`; this is not the requested full autonomous loop. |
| Deterministic trade diagnosis | Substantial implementation | `analysis.analyze/compare` and `diagnostics.py` calculate retained/removed/new trades, winners, session-close winners, excursions and fingerprints. Comparison explicitly avoids claiming a specific removed trade caused a replacement. Verify all requested M3/path and period outputs before extending. |
| Robustness | Partial | Sandbox preregistered bounded development/cost samples exist; separate candidate cost/regime/simplification services exist. They do not establish full-period robustness for a generated child. |
| Validation/final decisions | Implemented manual path; autonomous path partial | `validation.py`, `decisions.verified_validation`, `Decisions.record` verify immutable evidence and passing validation. Do not bypass these by relabelling development triage as acceptance. |
| Archived dependencies | Implemented with insufficient bound for some parents | `source_dependencies.archived_parent` statically selects archived modules, checks provenance and hashes, limits 50KB/32 modules. Current confluence chains can exceed that. Never substitute changed current files. |
| Generated execution | Implemented isolation; scale incomplete | `sandbox.py`, `sandbox_worker.py`, `sandbox_runs.py`: container-only generated code, parity, prefix tests, resource/deadline controls. Still one symbol/10,000 aggregate bars, maximum 600 seconds. Completed history is serialized on each RPC. |
| Discovery/idea mode | Partial | Curated campaign planning exists. A bounded family catalog is not unrestricted novel-idea research or literature synthesis. Evidence provenance and search-debt accounting must accompany any expansion. |
| Durability | Partial acceptance | Campaign documents, dispatch state and recovery exist. Repeat restart acceptance across the completed lifecycle; existing recovery tests do not prove unattended research quality. |
| UI | Partial | `AutonomousResearch.jsx` and `campaignView.js` expose campaigns, budgets, attempts and triage. Need a simple progression through the completed lifecycle and honest final disposition. |
| Paper/forward execution | Missing execution layer | `brokers/execution_provider.py` is explicitly disabled. Existing broker history adapters and canonical executions are read-only. No `ExecutionIntent`, `RiskGateway`, durable deployment or paper-order state machine was found. |

No inspected path has yet been established as obsolete/dead. Do not delete working
manual candidate workflows merely because autonomous orchestration is incomplete.
This audit identifies integration gaps; it does not certify every reachable path.

## Initial autonomy gaps

1. Full-period generated-child evidence cannot fit the current bounded sample
   execution design; long daily warmup can leave samples with no trades.
2. Raising the bar limit alone leaves repeated-history RPC growth and timeout risk.
3. Structural development triage stops before the existing candidate validation
   and decision workflow. A promising label grants no acceptance authority.
4. Manager recommendations do not execute all robustness/simplification actions.
5. Structural attempts, numeric hypotheses and family search debt need a coherent
   durable audit without losing the existing records.
6. Complex archived parent chains can exceed the author/dependency bound.
7. Mocked/Docker acceptance has not established real-model research discipline or
   overnight reliability for the requested complete lifecycle.

## Reuse and required additions

Reuse the canonical engine and completed-bar context; `market_concepts` causal
versions; research worker runtime; archived source store; campaign reservations;
dataset access firewall; existing deterministic diagnostics, candidate checks and
validation; canonical broker fills and Journal reconciliation; shared frontend
status/table components. Keep research workers isolated from broker services.

Required new or extended components: bounded incremental causal sandbox transport,
full-period child evaluation, autonomous action dispatcher and final disposition,
structural hypothesis/search ledger integration, frozen deployment repository,
completed-bar ingestion/checkpointing, independent shadow runtime, durable paper
intents and reconciliation, risk gateway, paper-only adapter, forward dashboard
and shadow/paper/Journal linkage. These are integration work, not just endpoints.

The requested B/C/D keys exist in the user's untracked
`vwap_d6_combined_confluences_research_v1.py`. Preserve that file. Any deployment
must pin the actual source bundle/configuration; never recreate its rules from
the names or silently switch source on refresh.

## Saved-run architecture and measured problem

`BacktestRunRepository.get_section` projects SQLite JSON; `runSections.js` bounds
the frontend cache to nine entries/30 seconds. `openSavedRun` requests summary.
Trades and analysis load on demand. This work already exists and must be reused.

Before this increment, `useSavedSettings` fetched the full run. Summary removed
trades/analysis but retained the entire equity curve. A temporary isolated
synthetic run (3,000 trades, 660,000 equity observations and diagnostic payload)
measured on 13 October:

| Existing path | Read + decode | JSON serialization | Response bytes |
| --- | ---: | ---: | ---: |
| Full run used by settings | 664.89ms | 879.63ms | 50,799,464 |
| Summary | 1,108.51ms | 922.19ms | 44,703,143 |
| Settings projection after fix | 38.84ms | 0.18ms | 226 |

Single local measurements, not browser/network or p95 results. The temporary
benchmark cleanup initially hit a Windows SQLite file lock after measurements;
no production data was touched. Repeat controlled measurements before acceptance.

Static hypotheses requiring browser profiling:

- `PerformanceChart`: full curve preparation, plateau-only reduction,
  `Intl.DateTimeFormat` constructed in tick/crosshair callbacks, effect dependencies.
- `StrategyLabPage`: Expand all creates every trade row, repeated `indexOf` lookups,
  repeated diagnostics, large analysis components.
- Runs list SQL extracts metrics from each large JSON blob.
- Summary's full equity projection delays useful content despite lazy trades.

Do not claim smooth scrolling or a sub-500ms useful paint until measured with a
heavy browser fixture. Preserve all source observations and numerical results.

## Compute follow-up

Previous exact-parity session normalization changes are present. The previous
three-month cache comparisons reported 15.3–18.0% wall-time reduction. Those were
all-day entry experiments, not proof of performance under the requested D6 window.
`research_runtime.py` already supports bounded independent process workers;
do not introduce a second pool or split one causal timeline. Profile repeated
session scans, pivot/FVG scans, context conversion and sandbox RPC before changes.
GPU use is not justified by the existing Python/pandas allocation measurements.

## Ordered commits and acceptance checklist

Order differs from the suggested sequence only to bring the independent current
responsiveness blocker forward and put causal execution before autonomous use.

- [x] 1. Current-state audit and acceptance ledger (small; this document).
- [x] 2. Initial heavy-run backend measurements and configuration-only settings copy (small).
- [x] 3. Profiled progressive loading, chart and trade-table improvements (medium).
- [x] 4. Incremental causal sandbox transport and bounded complex archived dependencies (large; full-period capacity ceilings are not throughput guarantees).
- [ ] 5. Full-period diagnostics and robustness integration (large).
- [ ] 6. Autonomous candidate lifecycle, authority and restart coverage (large).
- [ ] 7. Campaign UX and end-to-end discipline benchmark (medium/large).
- [ ] 8. Frozen deployment storage and independent shadow state (large).
- [ ] 9. Completed-bar ingestion, session handling and replay parity (large).
- [ ] 10. Mocked paper adapter, risk gateway and idempotent reconciliation (large).
- [ ] 11. Explicit approval controls, Journal linkage and Forward Validation (large).
- [ ] 12. Fault tests, compute follow-up and full regression/browser handoff (large).

## Safety and external acceptance

No live-money path, configurable live host or automatic research promotion.
Alpaca paper must use the hard allowlisted paper host, no redirect to another host,
and backend-only credentials. Persist intent before submission. A timeout must
reconcile by deterministic client order ID before any retry. Unknown state halts.
Disarm and flatten are distinct; fills must come from broker facts.

Review official Alpaca documentation before implementing the adapter. Mocked tests
must not call a broker. Actual paper-account and market-session acceptance require
the user's configured paper account and explicit arming in the finished UI.
Actual research-quality acceptance requires an opted-in configured/priced model.
These external acceptances must remain distinct from deterministic fixture passes.

Preserve all frozen strategy rules, saved results, existing read-only brokers,
dataset exposure history and generated-code isolation. No application/test work
in this phase may silently grant additional broker or holdout authority.

## First increment verification

13 October: 7 focused backend tests passed (`test_run_sections.py` and
`test_phase52_saved_runs_and_chart_series.py`), including configuration-only SQL,
exact saved configuration preservation, API response and missing-run handling.
133 frontend unit tests passed. Production build passed (154 modules; existing
955KB bundle advisory). Browser usability smoke passed settings copying without
a full-run request, loading feedback, lazy trades, Trade Review and existing
workflow regression at 1024/1440/1920 with no runtime errors or overflow.
This is not the heavy-run browser performance acceptance or final full-suite run.

Initial test attempts encountered local temporary-directory permissions and one
transient frontend test-process failure; explicit writable test directories and
serial frontend tests passed. The build initially encountered cache permissions
and transient unresolved imports for existing files; the authorized retry passed
without modifying those files. No migrations or strategy-rule changes.

## Viewer increment: 13 October

Reproducible tools: `backend/tools/benchmark_saved_run_viewer.py` (isolated SQLite,
660,000 observations, 3,000 trades) and
`frontend/tests/browser/heavy-run-performance.mjs` (opt-in CDP benchmark).
The before browser fixture mocked serialized summary responses; the after run
uses the actual isolated repository HTTP fixture and additionally retains 3,000
trade events. These are local development-mode samples, not p95 or production
network measurements. React StrictMode explains two chart setup calls.

| Measurement | Before | After |
| --- | ---: | ---: |
| Chart useful paint | 11,426.7ms | 3,665.3ms |
| Headline available | Not separately captured | 344.3ms |
| Summary payload | 103,581,823 bytes | 440 bytes |
| Deferred performance payload | Included above | 1,017,334 bytes |
| Browser JSON parse | 229.7ms | 0.1ms headline / 2.4ms performance |
| Curve preparation | 456–466ms per call | 2.3–3ms per call |
| Chart setup | 1,298–1,430ms per call | 12.6–19.3ms per call |
| Largest recorded long task | 2,783ms | None recorded during summary/chart/scroll sample |
| Maximum scrolling frame gap | 900ms | 5.7ms (headless, not a physical-display FPS claim) |
| Live DOM elements | 181 | 183 |

Artifacts: `C:/Users/jamie/Project/heavy-run-before-20261013.json`,
`heavy-run-after-20261013.json`, and `heavy-viewer-20261013/measurements.json`.
Fixture memory includes synthetic response strings; do not interpret its heap
as an application-only memory benchmark. Server projection still takes about
3.2 seconds for this cold full-curve read; it no longer blocks headline use.

Implemented: new overview/performance sections preserving legacy summary API;
deterministic display-only bucket extrema/event projection; explicit full detail;
stable empty trade data; cached Intl formatters; 20/100-row trade pagination and
indexed selection; unmount/request-generation guards. Snapshot/metric values
remain immutable. All original observations remain in full exports/detail.

Verified: 17 focused backend tests, 133 frontend tests, production build, heavy
trade paging and no page overflow at 390/1024/1440/1920. No eager Trades/Analysis.
Viewer item 3 remains open for cancellation-race/Analysis acceptance and final
full regression. Do not confuse this increment with completion of the major phase.

## Causal transport increment

Generated strategy RPC now sends only newly completed rows with explicit offsets.
The container reconstructs completed history, rejects discontinuous offsets and
copies context frames so a strategy's mutation cannot contaminate the next call.
Reset clears stream offsets and signal trace. Host completion indexes restrict
the copied/transmitted delta; future rows and derived post-trade columns remain
excluded. Wire provenance is `completed-bars-delta-json-v2`. The sandbox image was
rebuilt from its existing allowlisted context; all isolation/resource rules remain.

Synthetic 1,000-bar real-container comparison: legacy 19,613,495 request bytes /
9.92s; delta 256,780 bytes / 4.87s. This comparison preceded the additional indexed
host-copy optimization and is not a full-period capacity benchmark.
19 sandbox unit tests passed. Real Docker: 27 security/lifecycle/research-loop
tests passed; 31 dependency/author/reference/campaign integration tests passed
(the latter includes non-Docker tests). New container regression verifies history,
reset and mutation isolation. Logs reside in `C:/Users/jamie/Project/` with prefix
`delta-` and date `20261013`. Full-period evaluation remains unfinished.

## Full-period evaluation and historical warmup increment

New structural campaigns now pin the entire planned development period and its
historical warmup. Existing campaign documents without the new scope field keep
their original bounded authorization. An optional engine evaluation boundary
exposes completed warmup bars to strategy context without allowing orders,
positions or equity observations before the development period. Ordinary engine
runs retain the original default behaviour. Saved settings preserve that boundary.

Generated execution remains inside Docker. Full-period approval permits up to
1,000,000 aggregate input rows / 192 MiB of prepared frames for one symbol, within
the existing 512 MiB container and campaign time budget (absolute ceiling six
hours). Bounded approvals retain the 10,000-row / 600-second ceiling. Large initial
history is staged in 1,000-row chunks without calling strategy logic early or
raising the wire message-size limit. Timeout, memory exhaustion and discontinuous
history fail closed. This is a capacity ceiling, not a throughput guarantee.

Development triage now checks the full-period result alongside the preregistered
cost samples; good short windows cannot conceal a failing full-period result.
The cost samples remain bounded, and no unseen validation or deployment authority
is introduced. The larger autonomous acceptance/validation lifecycle is still open.

Focused verification: 78 engine/VWAP parity/Gold/Replay/research regressions passed;
13 warmup/campaign/real-container checks passed, including exact engine parity over
10,020 bars with 1,000 warmup bars and one continuous position across sessions.
The final full suite additionally covers the subsequent chunked warmup transfer.
133 frontend tests and the production build passed. Browser workflow regression
passed at 1024/1440/1920 without runtime errors. The complete backend run passed
1,250 tests in 613.70 seconds with real Docker acceptance enabled (one existing
Starlette/httpx deprecation warning). Log: `fullperiod-full-suite-20261013.log`.
No schema migration; additive saved configuration and campaign document fields.

## Archived dependency capacity — 14 October

The source-author and container now share a 128,000-byte bound for the complete
archived parent dependency closure (still at most 32 modules). Missing dependencies
fail closed; no current source substitution or truncation is permitted. Modules
remain inert on the host and are loaded only inside the isolated container.
Author evidence is bounded to 200,000 serialized bytes and the whole model request,
including instructions/schema/prior roles, to 240,000 bytes. Generated child source
retains its existing 50,000-character author limit.

The conservative input reservation increases to 250,000 tokens per call, without
cache discounts. Existing immutable monetary budgets are not enlarged. Campaigns
whose recorded provider quote no longer matches fail closed rather than silently
spending more. A new campaign may need a larger explicit budget; no paid model call
was made during this implementation. Automated boundary checks preserve exact
source bytes, reject an oversized bundle and reject oversized requests before HTTP.
Verified: 115 focused backend tests passed with real Docker enabled in 222.59s,
including oversized dependency inheritance inside Docker, author/campaign spending,
full-period parity, security, cancellation and crash cleanup. No research containers
remained after the run. The image was rebuilt from the allowlisted context.

## Complete development-window robustness — 14 October

New campaigns default to complete preregistered development windows at 1x and 2x
engine commission/spread/slippage. Parent, generated control, child and causal
prefix checks use the existing engine and isolated execution services. Warmup
remains separate from each evaluation period. Accounts reset independently per
window; these results are not summed into portfolio returns. Zero configured costs
remain explicitly insufficient cost-stress evidence.

The approval records `full_robustness_windows`; it requires full-period authority.
Older campaign snapshots without `structural_robustness` retain their original
seven-day samples. Dates remain fixed before results. Simulation counts are
unchanged (4 anchor runs plus 8 per window); time and memory bounds remain enforced.
This broadens development coverage, not locked-holdout access or deployment rights.

Verification: 99 focused tests passed with Docker enabled, including the mocked-
model/container campaign loop, cost parity and causality. An additional persisted-
policy regression verifies no silent scope upgrade. 133 frontend tests passed;
production build passed after a transient Windows dependency access-denied retry.
No production source change was needed for that build retry. The bundle-size
advisory remains. This is not completion of autonomous candidate acceptance or
forward/paper execution.

## Remaining Run Viewer acceptance — 14 October

The synthetic benchmark now computes canonical analysis breakdowns for its 3,000
trades. Deferred Analysis painted in 438.6ms, rendered 706 DOM elements, made one
Analysis request and did not mount a hidden performance chart. One 60ms long task
was recorded. No Analysis overflow at 1024/1440/1920; trade paging also passed at
390px. Headline appeared in 408.4ms and deferred chart in 3,919ms on this sample.
These are local headless development measurements while backend regression ran,
not production latency guarantees. Artifact: `heavy-analysis-browser-20261014.json`.

`run-open-races.mjs` verifies that a later selected run wins when responses arrive
out of order and that a late response cannot reopen an unmounted viewer. Integrated
settings, Trade Review, activity and navigation smoke also passed at three desktop
widths without runtime errors. No additional application changes were necessary.

## Verification closeout for these increments — 14 October

- Complete backend: **1,256 passed**, 616.71s, with `LEDGER_TEST_DOCKER=1`.
  One existing Starlette/httpx deprecation warning. XML/log artifacts:
  `C:/Users/jamie/Project/research-full-suite-20261014.{xml,log}`.
- Frontend: **133 passed**, zero failed/skipped; production build passed.
- Real Docker: included in the complete run; focused dependency/security/campaign
  run also passed 115 tests, followed by 99 robustness/campaign tests and one
  additional immutable-policy regression. These overlapping suites are not additive.
- Browser: integrated Trade Review/settings/navigation at 1024/1440/1920;
  heavy trade paging at 390/1024/1440/1920; Analysis at desktop widths; out-of-order
  and unmounted-result checks all passed. No runtime errors or page overflow.
- `git diff --check` passed. No Ledger research containers remained. Temporary
  benchmark servers and the isolated browser were closed. User strategy files and
  research outputs remain untracked and untouched. No schema migration.

This verifies commits through `e5ffdde`; it does not complete checklist items 6–12.
Item 5 now has full-period diagnostics and full development-window cost reruns;
autonomous regime/simplification and final candidate acceptance remain to integrate.
No live LLM/provider acceptance or paper execution was performed or enabled.

## Generated development-candidate freezing — 14 October

Promising full-period children with complete preregistered 1x/2x cost windows now
freeze into the existing candidate store as `GENERATED_DEVELOPMENT`, with state
`FROZEN_DEVELOPMENT`. The snapshot preserves exact inert source and archived
dependencies, parameters, parent identity, data/result fingerprints, Docker
provenance, frozen policy and development verdict. There is no schema migration.

Before freezing, the service rechecks result digests, recomputes summaries and
parent/child comparisons, checks the exact ordered cost-window coverage, verifies
control/prefix evidence and identical implementation/data across cost scenarios.
Insertion and its audit event are atomic, campaign-bound and idempotent. A restart
after insertion can reuse the same record rather than create another candidate.

The campaign report links the frozen candidate and records
`FROZEN_REQUIRES_VALIDATION`. The candidate UI distinguishes this from numeric
variants and does not offer their incompatible validation controls. This is a
development freeze, not acceptance, registration, activation, unseen-data approval
or deployment. Isolated generated-candidate validation remains the next integration
step; the existing numeric candidate/validation workflows remain intact.

Verification: **52 focused backend tests passed** in 159.02s with real Docker
enabled, including promising/non-promising campaign paths, evidence tampering,
immutable retry, untouched locked holdout and rejection by the incompatible numeric
validation endpoint. **133 frontend tests passed**, and production build passed
(existing bundle advisory; transient Windows file-access error cleared on retry).
The missing sandbox image was restored through the existing allowlisted builder.
No research containers remained. `git diff --check` passed.
The 1,256-test full-suite result above predates this increment; it is not claimed
as a full-suite run against these additional changes.

## Explicit isolated generated-candidate validation — 14 October

Frozen generated candidates now have a separate Docker validation action in
Research Agent → Advanced projects → candidate details. Select an untouched
dataset, enter fixed criteria, and explicitly approve its consumption. The
existing validation table and dataset firewall own the grant; no schema migration
or second validation registry is introduced.

Approval verifies the frozen source/dependency bundle, development evidence and
freeze audit identity, requires the exact development image, and reserves four
simulations before exposing data. The trusted parent runs in the ordinary engine;
generated control, candidate and prefix replay run only through Docker RPC. They
share the prepared validation data. Completed results retain comparisons, result
hashes, source/image/data/configuration identity and host implementation hashes.
Generated validation is explicitly rejected by the host job queue.

New structural campaign allocations leave one phase of compute capacity for
explicit validation. Approval atomically allocates it from the remaining campaign
budget to the reference project. It does not enlarge campaign limits. Existing
campaign reservations are unchanged: exhausted or expired campaigns fail closed.
No paid model calls are needed for this validation step.

Cancellation, timeout, provider failure, project pause and restart do not restore
unseen status. Restart marks an active generated validation interrupted, preserves
numeric validations, cleans this database's sandbox containers, and never retries
automatically. Repeating an identical approval returns its original grant.
The same runner lock serializes development and validation containers.

The browser supports consent, progress, result inspection and cancellation.
Acceptance remains separate: a validation pass does not activate/register source,
record final research acceptance or enable paper/live orders. Automatic
`one_frozen_candidate` orchestration, generated final decisions, simplification
and regime orchestration, and the forward/paper phase remain unfinished.

Verification results for this increment are recorded in the current handoff.
The earlier full-suite result is historical; this increment uses focused backend
regressions plus the complete frontend tests/build and mocked browser acceptance.

Final exact results: **137 focused backend tests passed**, 235.21s, with
`LEDGER_TEST_DOCKER=1`; one existing Starlette/httpx deprecation warning.
Log: `C:/Users/jamie/Project/generated-validation-closeout-20261014.log`.
Files run: `test_generated_validation.py`, `test_campaign_structural.py`,
`test_research_validation.py`, `test_research_decisions.py`,
`test_structural_candidates.py`, `test_research_director.py`,
`test_research_campaigns.py`, `test_campaign_projects.py`,
`test_campaign_launch.py`, `test_sandbox_research_loop.py`.
Frontend: **133 passed**, zero failed/skipped, using
`node --test --test-concurrency=1 tests/*.test.js`. `npm.cmd run build` passed
(156 modules; existing bundle-size advisory). Mocked browser acceptance passed at
1024/1440/1920 with no runtime exceptions or page overflow. The initial browser
fixture lacked the current Campaigns policy response/navigation; the fixture was
corrected, without changing application navigation.
Final Docker state: no labelled Ledger research containers. The isolated browser
and Vite server were closed. `git diff --check` passed; user confluence strategies
and research-output files remain untouched and untracked.

Significant files in this increment:

- New `backend/app/research_agent/generated_validation.py`: frozen-bundle checks,
  atomic grants/budgets, isolated execution and durable outcomes.
- `backend/app/research_agent/{sandbox_runs,validation,director}.py`: shared runner
  lifecycle, host-queue exclusion and capacity for explicit validation.
- `backend/app/api/research_agent.py`: explicit isolated approval/cancel routes.
- `frontend/src/features/strategy-lab/{ResearchCandidates,ResearchValidation}.jsx`:
  generated-candidate controls using the existing validation presentation.
- New `backend/tests/test_generated_validation.py` and extended
  `backend/tests/test_campaign_structural.py`: grant guards, failures/recovery,
  API consent and complete mocked-model/real-Docker development-to-validation path.
- New `frontend/tests/browser/generated-validation.mjs`: consent, endpoint choice,
  polling, cancellation, dataset exposure and three-viewport browser acceptance.
- This ledger and `RESEARCH_AGENT_FOUNDATION.md`: current status and limitations.

Manual check: in Backtest → Research Agent → Advanced projects, open the campaign's
reference project and its frozen generated candidate. Choose a still-untouched
dataset, set criteria, tick the consumption acknowledgement, and approve validation.
Observe the saved grant/result or cancel it while active. The dataset must remain
inspected after cancellation or failure. A repeat request must reuse the same grant.
An expired campaign or unavailable/mismatched sandbox image must refuse execution.
This requires an existing promising frozen candidate; a mocked passing fixture is
not evidence that a real strategy has an edge. No provider credentials or real
model calls were used in this increment's automated acceptance.

## Generated final research decisions — closeout 15 October

The existing immutable decision workflow now supports generated development
candidates. Acceptance verifies the frozen candidate audit and development evidence,
source/dependency/image identity, exact validation dataset and configuration,
control/prefix checks, parent/child result digests, recomputed comparison and
preregistered criteria. A persisted PASS label alone cannot override failing data.
No generated source is imported or executed during decision verification.

The existing structured review and explicit acknowledgement are required. Missing
simplification/regime checks remain documented limitations. Rejection can be recorded
without consuming holdout data. The frozen candidate and historical results remain
unchanged; accepting for research does not register, deploy or enable trading.

Candidate details now reuse `ResearchDecision`, with incompatible numeric manager,
cost/simplification/regime and sandbox-parent controls hidden for generated source.
The separate isolated validation controls remain available until a decision is saved.

Changes: new `backend/app/research_agent/generated_decisions.py` and
`backend/tests/test_generated_decisions.py`; integration in `decisions.py`,
`ResearchCandidates.jsx`, `ResearchDecision.jsx`; extended
`test_campaign_structural.py` and `frontend/tests/browser/generated-validation.mjs`;
this checklist and `RESEARCH_AGENT_FOUNDATION.md`. No schema migration.

Verification: **76 backend tests passed**, 151.14s, with `LEDGER_TEST_DOCKER=1`:
`test_generated_decisions.py`, `test_generated_validation.py`,
`test_research_decisions.py`, `test_research_validation.py`,
`test_campaign_structural.py`, `test_structural_candidates.py`.
Log: `C:/Users/jamie/Project/generated-decision-closeout-20261014.log` (artifact
name retained from the run started before this closeout).
An initial run passed 74 tests and failed two before execution because the sandbox
image was missing; the existing allowlisted builder restored it before the passing
repeat. One existing Starlette/httpx deprecation warning remains.

Frontend: **133 tests passed**, production build passed (155 modules; existing
bundle-size advisory). Mocked browser acceptance passed at 1024/1440/1920:
validation consent/cancel/polling, disabled acceptance without a passing validation,
required structured review and acknowledgement, final decision display, no numeric
research calls for generated candidates, no runtime exceptions or page overflow.
The existing Advanced projects duplicate React-key console warning was observed;
it is not included in the claim of no runtime exceptions. Temporary browser/server
were closed. No labelled Ledger research containers remain. `git diff --check`
passed. The complete backend suite was not rerun for this increment.

The passing acceptance fixture is synthetic and tests the verification gate, not
strategy quality. The real Docker fixture correctly produces insufficient validation
evidence (one winner, no observed loss denominator), blocks acceptance and permits
an explicit rejection. No real model/provider or trading calls were made.

Manual check: open a generated candidate in Research Agent → Advanced projects.
After isolated validation passes, select Accept for further research, complete all
five review fields, enter a rationale and acknowledge the decision. Without a pass,
acceptance must remain unavailable; rejection remains possible after active checks
finish. Saved decisions cannot be overwritten and must not enable any execution.

Remaining: automatic candidate-bound validation under frozen policy, generated
simplification/regime orchestration, automatic family disposition and coherent
research-debt/hypothesis integration, then independent forward shadows, paper-only
execution/risk/reconciliation and Journal linkage. This is not completion of the
full autonomous Research Agent or the requested forward phase.

## Policy-authorized automatic validation — 15 October

New structural executions freeze `one_generated_validation_v1` only when the
campaign policy explicitly selects `one_frozen_candidate`. The contract records the
policy hash and criteria: campaign minimum trade count, average R >= 0, and R profit
factor >= 1. Human approval remains the default. Existing executions without this
contract receive no retroactive authority.

After development completes, the director requires exactly one frozen generated
candidate and exactly one matching untouched campaign dataset. It does not rank
candidates or choose between multiple holdouts. Selection is committed before
dispatch and bound to candidate/hash, project, dataset and criteria. The existing
Docker validation runner rechecks this authority inside the budget/exposure
transaction. Automatic and explicit grants remain distinguishable in audit records.

Repeated coordinator ticks reuse the same grant without more simulations. Restart
reconciles the selected candidate and terminal/interrupted grant; no automatic
replacement candidate or interrupted-execution retry is allowed. Ambiguous selection,
changed policy, exhausted time/budget or dispatch failure yields REVIEW_REQUIRED.
The grant still uses the established dataset firewall and Docker-only execution.
A completed validation does not automatically accept, register or deploy source.

The campaign form now offers the holdout-policy choice under structural research,
with explicit dataset-consumption consent and stated criteria. Disabling model or
structural permission removes automatic holdout authority from the launch payload.
Campaign polling continues during validation, with status/reason and a cancel action
once a validation grant is active. During a reserved selection waiting for another
sandbox task, project pause/archive remains a way to prevent dispatch; there is not
yet a separate reservation-cancel control.

Changed files: new `backend/app/research_agent/campaign_validation.py` and
`backend/tests/test_campaign_validation.py`; `director.py`,
`generated_validation.py`, `sandbox_runs.py`, `test_campaign_structural.py`;
frontend `AutonomousResearch.jsx`, `campaignView.js`, `campaignView.test.js`,
`tests/browser/campaign-smoke.mjs`; this ledger and the short handoff. No DB migration.

Verification: **123 backend tests passed**, 189.79s, `LEDGER_TEST_DOCKER=1`, running
`test_campaign_validation.py`, `test_generated_validation.py`,
`test_generated_decisions.py`, `test_campaign_structural.py`,
`test_research_director.py`, `test_research_validation.py`,
`test_research_campaigns.py`. Log:
`C:/Users/jamie/Project/automatic-validation-final-20261015.log`.
The real-Docker fixture covers human and automatic validation, preserved source,
no host-queue execution, insufficient-evidence acceptance rejection and explicit
final rejection. Mocked policy tests cover ambiguous/missing candidates, changed
authority, expired deadlines, consumed datasets, budget limits, replay and recovery.

**135 frontend tests passed**, production build passed (155 modules; existing
bundle-size warning). The initial build hit transient unresolved imports in
unchanged files; the subsequent build passed without modifying those files.
Mocked browser acceptance passed at 1024/1440/1920 for policy choice, consumption
consent, launch, validation polling/cancel, navigation and overflow/runtime checks.
No labelled research containers remain; isolated browser/server closed.
`git diff --check` passed. Full backend suite was not rerun this increment.

Manual workflow: start a new campaign, enable structural research, select
Automatically validate one frozen candidate, review the criteria/consent, then
launch with adequate budget and Docker available. When exactly one candidate
qualifies, the backend consumes its matching holdout automatically. Review the
validation outcome and record any final research decision separately in Advanced
projects. Multiple candidates stop for review, not automatic ranking. Tests use
mocked models/data and do not establish real-model research quality or an edge.

Remaining: generated simplification/regime orchestration, automatic final family
disposition and coherent hypothesis/research-debt integration; full lifecycle/live
model acceptance; independent forward shadows and paper execution/risk/reconciliation
with Journal linkage. No live or paper orders are enabled by this increment.
