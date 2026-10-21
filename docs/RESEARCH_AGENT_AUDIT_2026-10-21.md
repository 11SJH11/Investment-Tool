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
3. Extend operation/event instrumentation to numeric trials, model requests,
   structural execution and result persistence; distinguish heartbeat, useful
   progress and operation age. Add paginated activity history. Read-only report
   polling now retries serially with 2.5–30 second backoff, retains the last
   successful report with a stale warning, and clears that warning on recovery.
   Campaign mutations are never automatically retried by this polling mechanism.
4. Add measured-duration estimates only for genuinely known remaining workloads.
5. Complete failure/security/model timeout/resume/browser-refresh verification,
   real Docker smoke in isolation, full suites and browser acceptance.
6. Report provider/model acceptance separately from deterministic mocked tests.
   Do not claim the Research Agent is fully working based on this partial audit.

## Overall product work still outstanding

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
