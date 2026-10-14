# Research, forward validation and responsiveness: current phase

Audit boundary: `8754cff`, 13 October 2026. This is an implementation and
acceptance ledger, not a completion claim. The untracked local confluence modules
and research outputs belong to the user and are preserved. No credentials read.

## Current-state audit

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

## Why the agent is not yet fully autonomous

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
- [ ] 3. Profiled progressive loading, chart and trade-table improvements (medium).
- [ ] 4. Scalable causal sandbox transport and complex archived dependencies (large).
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
