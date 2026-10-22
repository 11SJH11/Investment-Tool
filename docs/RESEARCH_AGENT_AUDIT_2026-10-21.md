# Research Agent audit and monitoring — in progress

This is an evidence log, not a completed comprehensive audit or release approval.
Continuation brief: the user's Research Agent technical audit/live progress request.

## Actual campaign diagnosis

Read-only inspection at 18:14 UTC on 21 October identified campaign
`15b7318e-94d7-4585-bbc6-1f1f4336dee8`, matching the 40-simulation / $1.89336
reservation in the brief. It had already ended before inspection:

- Persisted campaign state: DEVELOPMENT_COMPLETE.
- Only family: FAILED, error `baseline_compute_deadline`.
- Baseline queue job: `49b0af9a-df72-48dd-ad1b-f6a059f46c72`.
- Job created 15:57:07 UTC; last update 17:52:15 UTC, cancelled.
- Processed 209,408 of 790,767 bars (26.4816%); no saved run.
- BASELINE_FAILED event at 17:52:10 UTC; DEVELOPMENT_COMPLETE at 17:52:15 UTC.
- No completed baseline, numeric cycle or structural check for this family.
- Reserved resources are not actual simulations or confirmed model expenditure.

The backend process was present. Process presence does not prove a particular
task is healthy. Saved progress proves this baseline had started; it does not
provide a historical throughput trace or explain the slow execution by itself.
There is no remaining ETA for this cancelled job. No campaign was cancelled,
resumed, restarted or reconfigured by this investigation. Holdout was not read.

## Confirmed findings before changes

- **Critical:** none established so far; this is not a clean bill of health.
- **High — misleading successful closeout:** Director uses DEVELOPMENT_COMPLETE
  after all families stop, including failed families. Existing state semantics
  are preserved, but the read-only report and UI now derive FAILED or
  COMPLETED_WITH_ERRORS from terminal family evidence. Historical records remain
  untouched. This does not fix baseline computation speed.
- **High — baseline did not finish within its allocated compute deadline:**
  measured evidence above. The deadline was about 115 minutes. Root-cause profiling
  remains necessary; do not increase budgets or change frozen settings blindly.
- **Medium — queue evidence hidden:** the campaign page previously showed family
  counters and coordinator thread availability, without linked bar progress.
  Added indexed baseline/reference job lookup, status, IDs, processed/total bars,
  last persisted update and explicit family failure reasons.
- **Medium — heartbeat not progress:** a running coordinator thread is still not
  a measured heartbeat or useful-work signal. New display separates it from job
  evidence. More complete operation instrumentation remains outstanding.
- **Low — existing warnings:** Starlette deprecation and frontend bundle-size
  warnings; initial isolated build also hit transient existing-file resolution.

## Implemented first monitoring slice

`campaign_progress.py` reads only baseline/reference queue metadata. It does not
instantiate workers, inspect results or query holdout jobs. Existing active-page
polling refreshes the new `CampaignProgress` panel. Missing/invalid bar counts
remain indeterminate; campaign reservations are never a denominator for progress.
No ETA is fabricated from the wall-time ceiling or dynamic research budget.

A running job with no persisted update for ten minutes is labelled a suspected
stall, not a failure. This is a preliminary heuristic, not full context-aware
stall diagnosis. It does not stop or restart anything. Numeric/model/Docker work
is explicitly outside this panel's counts. Existing Docker timeline remains.

Existing pause/cancel/validation state logic is unchanged. No database migration.
The running backend was not restarted; these edits are not claimed deployed.

## Verification

Latest complete run including model monitoring: **1,922 passed, 41 skipped,
1 warning in 622.59s**, log `research-operations-full.log`. Frontend **144 passed**;
production build passed, 172 modules. Real Docker security/lifecycle **22 passed**
plus sandbox research-loop **9 passed** (31 total, 183.79s); no orphan Ledger
containers, unrelated stopped containers untouched. Production fixture browser
smoke passed at 390/1024/1440/1920px, including model operation presentation.
All logs are under `.ledger-test-artifacts/logs/research-operations-*`.

- MT5 recovery snapshot closeout, preceding monitoring edits: full backend
  **1,861 passed, 41 skipped**, 564.79 seconds; frontend **139 passed**; isolated
  production build passed, 168 modules.
- Monitoring changes: **75 focused backend tests passed**, including 11 new
  progress tests; **141 frontend tests passed**; isolated build passed, 169 modules,
  exit 0; diff check passed.
- Complete backend run after progress/FVG changes: **1,898 passed, 41 skipped,
  1 warning in 585.20 seconds**. Nine subsequently added MT5 clock diagnostic
  tests passed separately; they were not part of that full-run count.
- Reconnect repair: **144 frontend tests passed**; production build passed on
  retry. Initial attempt had intermittent resolution failures for existing
  DataTable/SymbolSearch files; no source change was needed for the retry.
- Production browser smoke before the reconnect repair passed at **390, 1024,
  1440 and 1920px**, including reload persistence, GET-only requests and no
  runtime errors. Responses were fixtures, not live research acceptance.
- **4 real Docker tests passed in 20.45 seconds**: readiness cleanup, Gold
  Sunday completed-frame control parity, hostile-code isolation, and mocked-LLM
  child/control/causality/result persistence. Image:
  `sha256:6a4bc6cdda48940131ad8283c0ef2ec8da0437262ffe5f47f0eb03bef06d2590`.
  Subsequent Docker inventory found no Ledger containers; six unrelated stopped
  containers were untouched. This was focused acceptance, not the entire Docker suite.
- Applied the read-only report function to the real campaign: FAILED, one cancelled
  baseline, 26.4816% bars, zero completed jobs. No user data writes.
- Evidence: `.ledger-test-artifacts/logs/campaign-progress-real.json`,
  `campaign-progress-frontend.log`, and `mt5-recovery-*`.

## Remaining Research Agent work

Confirmed performance hotspot repaired: the canonical FVG detector previously
created two pandas row Series per examined bar. Tuple iteration preserves the
existing calculations and observations; 26 oracle/prefix/future-tail parity tests
pass. An isolated 20,000-bar profile fell from 6.697s to 0.137s. This measures one
detector call, **not** whole-backtest speed. Frozen strategy rules were not edited.
The changed canonical implementation changes dependency provenance for future
runs; existing results/campaigns were neither rewritten nor rerun.

1. Continue profiling the Gold baseline on isolated frozen data; identify CPU, copying,
   indicator, queue-authorization and database costs without changing strategy rules.
2. Complete the requested end-to-end correctness/statistical audit: archived
   source/parameters, reset independence, warmup/alignment, causality, cost/leverage
   consistency, validation boundaries, attribution, budgets and model recovery.
3. Finish per-bar structural execution instrumentation and result-persistence
   timing; existing Docker phase events are not a per-bar heartbeat. Numeric
   queue progress, model role/metering, coordinator cycle timestamps and paginated
   campaign activity are implemented. Read-only report
   polling now retries serially with 2.5–30 second backoff, retains the last
   successful report with a stale warning, and clears that warning on recovery.
   Campaign mutations are never automatically retried by this polling mechanism.
4. Add measured-duration estimates only for genuinely known remaining workloads.
5. Complete failure/security/model timeout/resume/browser-refresh verification,
   real Docker smoke in isolation, full suites and browser acceptance.
6. Report provider/model acceptance separately from deterministic mocked tests.
   Do not claim the Research Agent is fully working based on this partial audit.

## Overall product work still outstanding

### Technical audit evidence matrix (22 October)

This matrix records inspected mechanisms and regression coverage. It does not
claim exhaustive formal verification or completion of real-provider acceptance.

| Area | Inspected implementation / regression coverage | Conclusion and limit |
| --- | --- | --- |
| Source identity | `source_dependencies.py`; `test_research_dependencies.py` | Archived dependency hashes must match the frozen parent; missing archives fail instead of using current files. |
| Parameter/control integrity | `trials.py`; `test_research_trials.py` | Control precedes variants; data/source mismatch blocks subsequent runs; explicit retry spends another attempt. |
| Reset independence | `robustness.py`; `test_research_robustness.py`, `test_research_infrastructure.py` | Each window/cost run uses independent engine state. No sum of independent returns is presented as a portfolio. |
| Time alignment / warmup | `sandbox_runs.py`, `sandbox_wire.py`; `test_research_sandbox.py` | Completed-bar views and delayed higher-timeframe availability are tested; warmup is checked against permitted dates. |
| Causality | `sandbox_runs.py`; real Docker prefix/control tests | Full/prefix signals must agree. Finite replay is evidence, not proof against arbitrary malicious code. |
| Costs | `robustness.py`; `test_research_costs.py`, `test_research_robustness.py` | Original and doubled execution costs rerun the engine. Zero doubled remains zero and is explicitly flagged. User campaign's zero-cost/300x assumptions were not altered. |
| Holdout firewall | `access.py`, `dataset_planner.py`, `validation.py`; foundation/validation/campaign-validation suites | Chronological boundaries do not move to obtain convenient unseen data; candidate-bound grants permanently consume exposure even after failure. Unknown external/manual exposure cannot be detected. |
| Research debt | `research_ledger.py`, candidate/retention modules; ledger/retention/simplification tests | Failed attempts and removed winners remain visible. Counts are descriptive; no multiplicity correction or proof of an edge is claimed. |
| Model budget/recovery | `committee.py`, `author.py`, `spending.py`; spending/committee/author/loop tests | Reservations survive failed/unknown calls; idempotent request keys prevent replay. Returned numeric usage is now retained even when authorization is revoked before validation. |
| Model operation visibility | `campaign_operations.py` | Allowlisted IDs, role, timestamps and metering only; no prompts, generated source, credentials or evidence in this projection. Legacy timing/cost remains unknown. |
| Isolation | `sandbox.py`, `sandbox_guardian.py`; sandbox/Docker tests | Generated code uses non-root, network-none, read-only containers with no host mounts/socket, 512MiB/1 CPU/64 PIDs and scratch-only writes. No host execution fallback. |
| Crash cleanup | independent guardian + owner-scoped restart cleanup | Guardian watches EOF and a wall deadline for its exact container. If Docker itself is unavailable, removal must be verified on recovery; no unconditional cleanup guarantee. |
| Queue/storage failures | backtest progress repair; director/trial/loop suites | Optional progress contention does not discard a run; mandatory persistence still fails. Coordinator stops after bounded storage failures. |
| UI recovery | `campaignPolling.js`, `CampaignActivity.jsx`; unit + production browser smoke | Serial bounded retries, stale report retention, cursor history paging, no mutation retries; backend must be restarted normally to load edited code. |

Additional confirmed **medium** finding fixed in this continuation: a committee
call could return usage and then lose that metering if the project was paused
before result validation. Reservations were already preserved, so this was not a
budget bypass. Usage is now captured before the authorization/validation gates.
The role is durably recorded before dispatch; failures do not automatically retry.
Coordinator cycle start/success timestamps are process-local and reset on restart;
they are supervision evidence, not a fabricated worker or simulation heartbeat.

### Manual acceptance for the monitoring changes

1. When existing work is idle, restart Ledger normally and refresh the browser.
   Development did not restart the user's backend or claim to deploy these edits.
2. Open Research Agent and select the failed Gold campaign. Its derived outcome
   should be FAILED with `baseline_compute_deadline`, the cancelled baseline job
   and its recorded 209,408/790,767 bars. Do not interpret 40 reserved simulations
   as 40 executed jobs or $1.89336 reserved as a reconciled provider invoice.
3. Inspect Persisted activity. Load older events and return to latest. A temporary
   request failure should leave the displayed page intact and allow retry.
4. During a separately authorized bounded campaign, inspect numeric control and
   variant states and model role/call metadata. Missing legacy timestamps/costs
   must remain unavailable. A returned model response is not a validated proposal.
5. Temporarily take only the browser offline: the last report should remain with
   a stale warning; restoring connectivity should recover without relaunching
   or retrying a mutation. Backend jobs do not depend on this browser.
6. For an explicitly authorized structural run, inspect the existing Docker
   timeline and control/prefix evidence. A long `backtest_running` phase is not
   a per-bar progress estimate. Failed checks must not release a candidate.
7. Do not enable or infer T01 execution from this page. Research never deploys a
   strategy, places orders, or grants MT5 account execution authority.

The subsequent controlled baseline below supersedes the earlier absence of a
completed genuine development run. It is not a rerun of the campaign state machine
or a complete numeric/structural/model campaign acceptance.
No live paid-model acceptance was triggered. The adapter has per-request network
timeouts and input/output bounds; this audit has not established a hard total
wall-time kill for a provider that trickles response bytes indefinitely. The
Docker strategy wall-time watchdog is a separate, tested mechanism. No overall
ETA is supplied for dynamic model-driven work. Large-history report latency
outside the now-paged campaign events still needs measured profiling.

### Genuine cached Gold baseline completed (22 October)

Explicitly authorized isolated verification used the failed campaign's original
development dates (2023-08-14 through 2025-11-05), warmup from 2022-10-23, unchanged
strategy parameters, $10,000 balance, 1% risk, zero costs and 300x leverage. The
current corrected strategy/concept implementation and current cached OANDA-mid
data were fingerprinted; historical failure provenance was not overwritten.

- **Completed in 6,408.813 seconds (106m49s)**, below the original **6,900-second
  (115-minute)** allocation, with approximately 8m11s remaining.
- 1,074,537 cached 1m rows and 71,892 cached 15m rows including warmup; 790,766
  evaluated primary bars reported during execution. Bounded reads use exclusive
  end time; the earlier failed queue reported 790,767, so this is not a claim of
  bit-for-bit identity with the old incomplete run's inputs.
- 410 trades; total R 30.006435; average R 0.073186; R PF 1.192349. These describe
  frictionless development assumptions, not realistic execution or an edge.
- Result SHA256: `c34d33da67e692998e30154e8a767d3173f25fe3590b0e9c0dd258b7bb93be5a`.
- Artifacts: `backend/data/research_verification/gold-20261022T082249630831Z/`
  (`manifest.json`, `progress.json`, `result.json`). Digest rechecked after completion.
- User DB opened read-only; existing failed campaign still FAILED at family level
  with `baseline_compute_deadline`. No provider calls, credentials, holdout reads,
  model requests, deployment, order placement or user service restart.

The opt-in verifier refuses window changes and protected/validation overlap,
restricts cached data to XAUUSD 1m/15m and records a separate output. Three verifier
tests passed, including unchanged source DB bytes and refusal before execution.
The preceding 1,922-test full run predates these three tool-only tests. Completion
margin is modest; performance remains a priority and no settings were tuned.

### 2026-10-22 activity and numeric-progress continuation

Campaign reports now return the latest 50 persisted events rather than the entire
history on every poll. A read-only `/research-campaigns/{id}/activity` endpoint
provides exclusive-ID cursor paging (maximum 100 events), supported by an
idempotently created `(campaign_id,id)` index. No event is deleted. The UI shows
one bounded page, supports older/latest navigation, preserves the displayed page
on failure and offers retry. New concurrent events cannot shift an older cursor.
The compatibility `events` field contains only that latest page in chronological
order; complete history is available through the activity endpoint.

Queue progress includes baseline/reference and current numeric control/variant
attempts. Numeric trial/cell status is copied from persisted records, not inferred
from reservations. Old attempts and unrelated projects are excluded; payloads and
results are not returned by this progress query. Model calls and Docker execution
remain outside these simulation counts. Their complete operation instrumentation
is still outstanding, as is the full correctness/statistical audit.

Verification: **80 focused backend tests passed** (including nine activity and two
numeric-progress regressions), **144 frontend tests passed**, production build
passed. Production fixture browser smoke passed at **390/1024/1440/1920px** with
history-request failure/retry, older/latest navigation, reload, GET-only requests
and no runtime errors. The final numeric build was also smoke tested. Existing
chunk warning remains; an earlier build attempt hit the intermittent existing-file
resolver failure and passed on retry. `git diff --check` passed. No full backend
rerun in this incremental step; the previous 1,898 result predates these changes.
No real database/service restart, campaign mutation, paid call or order submission.

- MT5: automatic timestamp diagnostics can establish the current offset, but not
  an unobserved seasonal rule. Demo quote samples at 18:18 UTC showed advancing
  ticks about 10,801 seconds ahead of receipt. No conversion has been applied.
  MT5 docs say returned bars are UTC:
  https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesrange_py
  The installation-specific discrepancy and exact server transition rule remain
  unverified. Samples are in `backend/mt5-demo-clock-latest.json` under test artifacts.
- MT5 submission/protection/account-wide recovery and explicit demo acceptance
  remain incomplete. Native demo Algo Trading permission is enabled; Ledger is
  still unable to submit orders. T01 is not running.
- Frozen T01 deployments, durable candle frontiers, management/pause semantics,
  Journal attribution and the Algo Trading monitoring dashboard are not complete.
- Screenshot/annotation system remains pending, followed by the previously scoped
  Replay/evidence, performance, notifications and safe artifact cleanup work.
- Live-money execution and distributed hosting remain deferred. No claim of
  live trading, strategy profitability or automatic deployment is made.

### Docker operation visibility continuation

Sandbox runs now persist host engine progress at most once every two seconds.
Cancellation/deadline/project-authority checks still run on every callback.
Parent control has its own phase; generated control/candidate/prefix runs retain
their existing distinct phases. Each save records an update timestamp. The
campaign operations projection returns only allowlisted progress and the last ten
lifecycle events for linked projects, with no source, results or raw errors.
Progress from an earlier phase is suppressed. More than ten minutes without a
persisted update is labelled a possible stall, not worker death or retry authority.
Legacy records with no update timestamp remain explicitly unknown.

This is not a per-tick container heartbeat. A blocking remote callback cannot
report host bar progress. Preparation and robustness phases may remain coarse;
no fabricated global ETA or automatic recovery was added. Generated code still
executes only inside the existing restricted Docker worker.

Verification: five operation tests passed; structural/operation focused suite
16 passed, six opt-in cases skipped. A stale structural fixture lacked the real
sandbox table's project_id column; its schema was corrected without weakening
assertions. All 31 opt-in real Docker tests passed in 192.89s. Frontend 144 passed;
production build passed; fixture browser smoke at 390/1024/1440/1920px passed with
Docker counts/stall indication, model metering, activity paging/retry and reload.
Full-suite closeout is recorded in the current handoff after completion.
