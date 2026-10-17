# Research, forward validation and responsiveness: current phase

Audit boundary: `8754cff`, 13 October 2026. This is an implementation and
acceptance ledger, not a completion claim. The untracked local confluence modules
and research outputs belong to the user and are preserved. No credentials read.

## Current: exact B shadow/paper comparison (17 October)

`forward/comparison.py` reads closed B Journal rows without altering them. Matching
requires experiment, frozen definition fingerprint, symbol, direction and exact
entry decision. For frozen next-open market shadows, the checkpoint at the entry
open must contain the pending market signal with the same decision time/direction;
its checksum is verified. Paper requires a checksum-verified recorded entry
decision. Missing evidence and duplicates remain unresolved, never nearest-time
matches. Different definitions cannot match. No engine or trading-rule changes.

Forward report/API and `ForwardComparison.jsx` expose matched count, both Journal
IDs, missing closed counterparts and ambiguous/evidence-unavailable cases. Positive
entry/exit slippage per share means adverse execution for the trade direction.
P&L difference is null if either side is unknown; it may reflect differing sizes
and costs. Duration difference requires broker-completed-fill timestamps for all
paper aggregates. Submission/individual-fill latency remains null. A missing
closed counterpart may still be open or not imported; it is not proof of a missed
trade. Small-sample limitations are visible. No schema migration.

Verification: **142 passed**, one existing warning, 45.37s across `test_paper*.py`,
`test_forward*.py`, `test_broker*.py`, `test_canonical*.py`; **136 frontend passed**.
Production build passed (161 modules, 981.64 kB JS / 285.01 kB gzip). Initial build
had intermittent import-resolution errors on unchanged existing files; retry
passed without changes. Existing chunk-size warning remains. Mocked forward and
comparison browser checks passed at 1024/1440/1920, no page overflow/runtime errors.
No real orders/model calls. Full backend not rerun this increment.

Remaining: complete metrics, session replay/parity workflow, latency evidence,
operational risk acceptance and opt-in real-provider/model acceptance.

## Previous increment: reconciled paper Journal import (17 October)

`forward/paper_journal.py` converts terminal, reconciled cumulative order fills
into the existing canonical `Execution` model and `BrokerSyncRepository`. It does
not fetch broker data or submit orders. The backend paper monitor invokes it after
coordination; failures disarm through the existing review-required path.

Stable identity includes provider/environment/account/deployment/order. A complete
entry/exit quantity balance is required before publishing one closed Journal row.
Pending aggregates remain unpublished; canceled partial entries and multiple
partial exits preserve actual quantities and weighted prices. Resync preserves
Journal reviews and IDs. Unknown costs, net P&L and R stay null, not zero or an
estimated broker result. Provider completed-fill timestamps are distinguished
from first-observed-fill timestamps. Ambiguous chronology fails without committing.
Raw account IDs are hashed before canonical storage/Journal metadata.

Frontend labels these as Alpaca automatic paper; existing broker read-only review
behavior applies. No schema changes or frozen strategy/engine changes.

Focused checks: **35 passed**, one existing warning, 15.98s, covering paper Journal,
service, gateway, protection and shadow Journal. **136 frontend tests passed**;
production build passed (160 modules, 979.77 kB JS / 284.66 kB gzip, existing chunk
warning). Full-suite 1,439/38 below is the previous increment, not this tree.
No real broker orders/model calls or new browser acceptance were performed.

Broader regression: **136 passed**, one existing warning, 39.48s: all
`test_paper*.py`, `test_forward*.py`, `test_broker*.py` and `test_canonical*.py`.
Basetemp: `C:/Users/jamie/Project/paper-journal-regression-1017`.
`git diff --check` passed. User strategy modules/research outputs remain untouched.

Still unfinished: exact shadow/paper decision matching, submission/fill latency
evidence, complete Forward Validation metrics and session replay/parity workflow.
The existing shadow checkpoint retains pending-entry decision evidence; matching
must validate this evidence rather than pair trades by nearby timestamps.

## Previous increment: automatic shadow Journal linkage (16 October)

Closed Baseline/B/C/D shadow trades now project automatically from durable runtime
state into Journal. Each deployment is a separate account identity; stable IDs
include deployment, entry time and direction. Repeated polling/restart does not
rewrite an existing row or its reviews/attachments. A changed closed result fails
instead of silently replacing published execution facts. The service retries the
projection for stopped/halted deployments too, when configured.

Source `forward_shadow` is labelled **Forward · simulated shadow**. Execution
facts are read-only, with normal review fields and attachments still available.
The metadata retains the exact engine trade, frozen source/archive, definition,
parameters, costs, feed identity and forward start. This does not claim broker
fills or establish a matched B paper counterpart. Paper Journal import and exact
decision-based matching remain unfinished.

Schema: a preserving source-constraint migration admits `forward_shadow`; existing
columns, rows, IDs, attachment links, indexes/triggers and autoincrement high-water
mark are preserved. Custom incoming foreign keys stop migration rather than risk
cascading deletion. No production database was opened for development.

Focused checks: **33 passed** (15.02s), including migration/repeated initialization,
independent shadow identities, review preservation and immutable published facts.
Frontend: **136 passed**; build passed (160 modules, 979.71 kB JS, existing chunk
warning). Mocked Forward Validation and isolated shadow TradeDetail browser checks
passed at 1024/1440/1920: simulated provenance/read-only facts/review controls,
no overflow or runtime errors. Final full backend: **1,439 passed, 38 skipped**,
one existing Starlette warning, 510.89s. Command from `backend`:
`.venv/Scripts/python.exe -B -m pytest -q --basetemp C:/Users/jamie/Project/forward-journal-full-1016`.
Log: `C:/Users/jamie/Project/forward-journal-full-1016.log`. `git diff --check`
passed. Isolated browser/Vite processes were stopped. No real orders or model calls.

## Previous increment: connected paper controls (16 October)

The user approved post-fill and cancel/replace protection gaps for paper only.
This supersedes the historical approval gate below. A backend-owned five-second
monitor and explicit configure/consent/arm/disarm/cancel/flatten UI are connected.
Configuration never arms trading. No real orders were placed during development.

MOC protection is confirmed from broker facts. Partial entries cancel their
remainder before protection; exits wait for confirmed MOC cancellation. Within
the final ten minutes of the provider session, exits defer to the closing auction.
Disarming entries preserves MOC protection; explicit cancellation can remove it
and requires review. Restart disarms entries and reconciles orders. Initial stops
are recorded, not installed broker-native catastrophic stops. Closing orders are
not guaranteed fills. Real-provider/shortened-session acceptance remains pending.

Verification: **1,436 backend passed, 38 skipped**, one existing warning, 492.81s
(`C:/Users/jamie/Project/paper-connected-full-1016.log`). **44 focused tests passed**,
21.06s. **136 frontend tests passed**. Production build passed: 160 modules,
979.61 kB JS / 284.59 kB gzip, existing chunk warning. Mocked browser acceptance
passed at 1024/1440/1920 including paper consent and controls, no overflow/runtime
errors. Prior 29-pass Docker verification applies to unchanged sandbox code.
No new schema migration; protection uses existing paper documents.

Remaining: Journal linkage, forward metrics/comparison and session parity,
operational risk acceptance and opt-in actual IEX/paper/model acceptance.
The current phase remains incomplete; the next MT5/results phase remains gated.

## Historical: forward deployment persistence foundation (16 October)

### Independent B paper decisions and broker-close gate

After `c543237`, added `paper_evaluator.py` and `paper_coordinator.py` plus focused
tests. B decisions use actual reconciled broker quantity/average entry and a
separate strategy instance; they do not copy B shadow positions or infer fills.
Each decision preserves broker observations, bar completion, evaluation time,
runtime identity and signal. Restart replays recorded contexts and checks exact
decision equivalence. Missing decisions, changed source, checksum corruption and
stale data fail closed. This is trusted frozen B only, never generated code.

Dispatch reservations precede broker requests. An interrupted reservation cannot
automatically reissue an order. SQLite owner fencing prevents an older gateway
process from arming/submitting after takeover; the bounded POST is fenced while
its pre-existing intent remains durable. Database-failure fixtures verify zero
POSTs before intent persistence and lookup-only recovery after a successful POST
whose acknowledgement could not be persisted. Three entry attempts conservatively
include rejected attempts. Initial strategy stop is recorded; this is not yet an
installed broker-native stop order.

Explicit cancellation does not assert flattening. Explicit flatten works while
disarmed or over the daily-loss limit, but unknown orders still block it. Partial
positions remain open until broker facts say otherwise. For partial fills without
a broker completed-fill timestamp, the context labels its timestamp as first
observed fill; it does not pretend that observation is an exact execution time.

The user selected **broker-managed close protection before enabling paper**.
The paper transport/gateway now supports documented market orders with `cls` TIF
for an already reconciled position, a conservative session-close-minus-ten-minute
submission cutoff, fixed paper host, durable IDs, lookup on unknown outcomes and
exact covered-quantity checks. Ordinary exits cannot bypass an outstanding MOC:
cancellation must first be reconciled. No MOC has been submitted to a real account.

Important provider limitation: Alpaca's documented bracket/OTO groups provide
price-based conditional exits, not an atomic entry-plus-MOC. Ordinary exits require
an existing position. Therefore a post-fill MOC leaves an unprotected interval;
partial entries and cancel/replace transitions add further gaps. A native closing
order is also not a guaranteed fill. Sources:
[order groups](https://docs.alpaca.markets/us/docs/orders-at-alpaca) and
[MOC/TIF request contract](https://docs.alpaca.markets/us/reference/postorder).
The calendar-relative early-close cutoff is deliberately conservative and still
requires real-provider acceptance; do not assert verified shortened-session behavior.

**Production coordinator arming is disabled** pending the user's explicit decision
on accepting post-fill protection gaps. No UI/API activation has been added.
The older pre-close coordinator branch is tested internal groundwork, not the
approved protection mechanism and must not be enabled as a substitute. No hidden
live-host switch exists. Research Agent cannot obtain an execution capability.

Additive on-use tables: `forward_paper_owner`, `forward_paper_decisions`,
`forward_paper_dispatches`. Existing tables/data remain intact.

Focused verification: **34 paper tests passed**, 15.39s, running
`test_paper_coordinator.py`, `test_paper_evaluator.py`, `test_paper_gateway.py`,
`test_paper_client.py`. An earlier full backend run passed **1,422**, skipped **38**,
one existing warning, 527.54s. That run began before the final fencing/fault/MOC
additions; a final-tree full run and real Docker checks are being recorded below.
Frontend has not changed since its 136-pass/build/browser verification above.

Final-tree full backend result: **1,429 passed, 38 skipped, one existing warning**,
520.97s. Command: `.venv/Scripts/python.exe -B -m pytest -q --basetemp
C:/Users/jamie/Project/forward-final-1016` from `backend`; log:
`C:/Users/jamie/Project/forward-final-1016.log`. Skips retain their opt-in markers;
this is not a claim that every external acceptance path ran.

Separately with `LEDGER_TEST_DOCKER=1`, `test_research_sandbox_docker.py` and
`test_sandbox_research_loop.py`: **29 passed**, one existing warning, 165.65s;
log `C:/Users/jamie/Project/forward-docker-1016.log`. This includes real container
security/resource/lifecycle tests and mocked-LLM research-loop control/prefix checks.
No sandbox rebuild was needed: the optional host-engine change did not alter the
allowlisted image inputs. Docker inspection after completion found zero Ledger
research containers and the same six unrelated stopped containers. Browser/Vite
processes created for the smoke test were stopped. `git diff --check` passed.

The SQLite process fence deliberately holds a write lock across a single bounded
paper POST. Assess its effect on other writes before operational paper integration;
it currently cannot affect ordinary use because paper is not connected to the app.

Remaining independent requirements are not hidden by this protection decision:
automatic Journal linkage, comprehensive Forward Validation metrics/comparisons,
session replay/parity workflow, complete paper lifecycle/controls, actual IEX
coverage acceptance and paper/model external acceptance. The next MT5 phase remains
behind the original completion gate.

### Subsequent increment: completed-bar shadows and paper boundary

Current phase remains **NOT COMPLETE**. The next MT5/compute/results phase from
attachment `925ddff5-de5a-432f-84bc-4a5aae11b79b/Pasted text.txt` remains gated.

Implemented an optional incremental BacktestEngine state with explicit provider
session closes; ordinary batch behavior is preserved. Four independent instances
consume one immutable raw IEX minute log. Availability must equal bar start + 1m;
incomplete, missing, revised, out-of-order and corrupt history fail closed. The
native historical engine completion contract remains unchanged. Restart rebuilds
strategy state by replaying the immutable prefix and compares saved evidence.
Source/runtime drift halts rather than upgrading frozen experiments.

Backend-owned preparation and polling survives navigation. Explicit consent starts
preparation; stopping a queued request durably prevents later activation. UI shows
four states, counts, equity and frozen definitions. Required warmup is 60 complete
provider sessions; IEX is not SIP and sparse IEX history may prevent activation.
Calendar is frozen with 90 days of future coverage; automatic horizon extension is
not implemented. No bars are fabricated. No real-feed entitlement/data acceptance
was attempted. This is not a live performance claim.

Paper-only transport has a fixed host, no redirects, no automatic POST retry,
short-lived internal order authorization and sanitized provider errors. The
unconnected gateway reserves durable deterministic client IDs before submission,
uses whole shares bounded by fixed notional and equity fraction, reconciles broker
fills/positions, disarms on restart/fault and does not infer fills from submission.
Tests cover partial/final fills, exits, duplicate requests, unknown outcomes,
account/position/order mismatches, backward fills, loss limit and stale decisions.
This is a foundation, not an operational paper executor: no API/UI arming yet.

Additive on-use tables: `forward_feeds`, `forward_bars`, `forward_checkpoints`,
`forward_preparations`, `forward_paper`, `forward_paper_intents`. No destructive
migrations. Existing experiments/deployments and source archives are reused.

Verification: **125 backend tests passed**, 42.30s, one existing Starlette warning:
`test_forward_deployments.py`, `test_forward_alpaca_data.py`, `test_forward_bars.py`,
`test_forward_runtime.py`, `test_forward_service.py`, `test_incremental_engine.py`,
`test_paper_client.py`, `test_paper_gateway.py`, `test_phase5_engine.py`,
`test_gold_experiments.py`, `test_vwap_session_performance_parity.py`.
Actual locally installed Baseline/B/C/D streamed-versus-batch fixtures pass.
**136 frontend tests passed**, zero skips/failures; production build passed,
159 modules, 974.63 kB JS / 283.36 kB gzip (existing bundle warning).
`tests/browser/forward-smoke.mjs` passed 1024/1440/1920 with mocked APIs: explicit
consent, request contract, four rows, stop, no page overflow/runtime errors.
Initial browser fixture omitted the existing jobs response; fixture corrected.
No application change was needed for that failure. `git diff --check` passed.

Remaining: independent broker-position-driven B evaluator, safe paper controls,
order cancellation/flatten/no-overnight enforcement, complete restart/fault tests,
Journal linkage and forward comparison metrics, full backend/Docker acceptance and
real provider/model acceptance where authorized. Do not label this phase complete.

Provider contracts: [Alpaca bars](https://docs.alpaca.markets/us/reference/stockbarsingle-1),
[market-data coverage](https://docs.alpaca.markets/us/docs/market-data-faq),
[calendar](https://docs.alpaca.markets/us/v1.4.2/reference/getcalendar-1),
[client-ID lookup](https://docs.alpaca.markets/us/reference/getorderbyclientorderid).

### Earlier persistence-only increment

Checkpoint 8 has started, not completed. `app/forward/deployments.py` prepares an
atomic group of four inactive shadow definitions using the exact installed
Baseline/B/C/D registry keys and frozen D6 settings. No source files were edited
or imported from an archive. The registry execution lease prevents source-refresh
races; the existing content-addressed source archive preserves loaded bytes.
Definitions pin effective parameters (including existing extra defaults), source
identity, required timeframes, QQQ/1m, explicit account/risk/cost assumptions and
the requested exchange-local session/M3/no-overnight/leverage constraints.

Each deployment has a distinct ID and independent serialized initial position,
pending, strategy/daily state, M3 count, equity and trade history. All remain
`DRAFT`, with no start/decision/FUTURE_OOS timestamps and execution disabled.
This is persistence preparation, not an incremental shadow evaluator. There is
deliberately no activation endpoint or broker call. Missing strategy keys fail
the entire group, never substitute another strategy. Request-key retries return
the original definitions even after source refresh; changed account settings
require a new request. Definition/source tampering fails integrity verification.

Additive, on-use tables: `forward_experiments`, `forward_deployments`; source
storage reuses `strategy_source_blobs` and `strategy_source_archives`. Existing
application initialization/data remain intact. No production database was used.
New files: `backend/app/forward/__init__.py`, `deployments.py`, and
`backend/tests/test_forward_deployments.py`. These docs are the only other edits.

Verification: **35 tests passed**, no skips/failures, 8.22s:
`test_forward_deployments.py`, `test_strategy_source_archive.py`,
`test_strategy_refresh.py`. Includes all four actual installed strategy contracts,
restart/idempotency, independent initial state, atomic rollback, invalid inputs,
archive tampering and repeated initialization. Test databases are temporary.
No frontend/application wiring changed; frontend build and full backend suite
were not rerun in this foundation increment. No orders or data-provider calls.

Next: bind a selected data-provider identity, implement completed-bar persistence
and checkpoints plus independent causal runtime state, establish shadow/backtest
parity including session-end behavior, then expose activation controls. Source
archives exclude engine/external dependencies and are not complete executable
environments; runtime compatibility must be pinned/checked before activation.
Paper execution/risk/reconciliation and Forward Validation UI remain outstanding.

## Continuation: declared generated development regimes (16 October)

New campaigns may preregister up to three named, chronological, disjoint regime
periods within each family's frozen development range. Each needs a definition
and evidence source. Labels are user assumptions, not verified classifications;
Ledger does not choose periods from profitable results. Empty is the default.
Existing campaigns retain their saved authority.

The Director reserves eight additional engine simulations per regime per
structural attempt before model work. Original compute/deadline limits remain.
The author receives the fixed declarations. Execution reuses the existing Docker
parent/control/child/prefix path at original and doubled costs, with the dataset
firewall and identical data checks. Regime cells remain separate from chronological
windows, with independent account resets; they are not a portfolio or holdout.
Missing, low-sample or adverse regime evidence blocks development promotion.
Freezing checks labels/dates, source/image identities, result hashes, paired
comparisons and causality evidence. No new execution or acceptance authority.

UI: enable structural research, expand Optional declared development regimes,
add periods/definitions/sources, review costs and consent, then start. Dates must
fit the automatically prepared development range for every selected family;
invalid dates or insufficient budget stop before model calls. Reports show the
declared definitions and parent/child N and expectancy separately at each cost.

Files: backend research-agent `regime_plan.py` (new), `campaign_policy.py`,
`director.py`, `author.py`, `structural.py`, `sandbox_runs.py`,
`structural_candidates.py`, `research_verdict.py`, `campaign_report.py`;
`test_generated_regimes.py` (new), `test_campaign_structural.py`; frontend
`CampaignRegimes.jsx` (new), `AutonomousResearch.jsx`, `campaignView.js`,
`campaignView.test.js`, `tests/browser/campaign-smoke.mjs`; this ledger and handoff.
No schema migration, trading rule, engine-accounting or Replay changes.

Verification: **163 backend tests passed**, zero failures/skips, 288.19s with
`LEDGER_TEST_DOCKER=1`, including six real-Docker campaign scenarios. Suites:
`test_generated_regimes`, `test_campaign_structural`, `test_research_verdict`,
`test_structural_candidates`, `test_research_campaigns`, `test_campaign_report`,
`test_research_director`, `test_campaign_validation`, `test_feature_ablation`,
`test_family_disposition`. Log: `C:/Users/jamie/Project/regimes-docker-1016.log`.
The new Docker case asserts 28 trial simulations, separate regime cells at both
cost levels, control/prefix evidence and compact parent/child reporting.
Also passed: 136 frontend tests, production build (158 modules; existing large
bundle warning), mocked browser acceptance at 1024/1440/1920 with no runtime
errors/page overflow, 75 backend compatibility tests (one opt-in Docker skip),
and two additional development-bound/budget authorization tests. An earlier
focused run passed 100 tests with six opt-in Docker skips. Counts overlap and
must not be summed. Full backend suite has not been rerun in this increment.
Final Docker inspection found no Ledger research containers; the same six
unrelated stopped containers were untouched. Test browser/server were closed.
`git diff --check` passed. No paid model or live provider was called.

Remaining broader phase: real-model research quality/lifecycle acceptance,
independent frozen forward shadows, paper-only B execution, risk/reconciliation,
Journal/Forward Validation linkage and final phase-wide verification. Regime
classification is not automatically inferred or validated. No paper orders are
enabled by this work.

## Continuation: iterative campaign / coordinator restart acceptance (15 October)

Extended the existing real-Docker campaign acceptance with two distinct synthetic
generated children under one frozen two-attempt budget. The first suppresses
entries and produces insufficient evidence. After that terminal result is saved,
the test closes/recreates the Director and resumes the same campaign. The second
author receives the first attempt and development search history, emits a neutral
gate with different source identity, and the existing simplification gate rejects
it for adding no observed benefit. Final disposition is abandoned development;
the holdout remains locked and no candidate is frozen.

Assertions cover eight mocked model calls, two distinct source hashes, 40 reserved
engine simulations across the children, unchanged campaign reservations, durable
attempt history, matching closeout/report, and three additional coordinator ticks
without another model call/job or any campaign mutation. Every child uses the
existing full-period, original/doubled-cost, control-parity and prefix-causality
Docker path. This is a coordinator restart after a completed attempt, not a claim
of process-death recovery during an in-flight container or a live-model quality
benchmark. Existing crash/security tests remain separate.

Verification: **14 structural campaign tests passed**, zero failures/skips,
**210.64s**, `LEDGER_TEST_DOCKER=1`; five real-Docker scenarios, including the new
iterative path. Command: `.venv/Scripts/python.exe -B -m pytest
tests/test_campaign_structural.py -q` from `backend`, with a unique temporary
database root. Log: `C:/Users/jamie/Project/iteration-acceptance-20261015.log`.
No application/frontend/schema changes: only this existing test file and two
handoff documents. The preceding 207-test focused run, 135 frontend tests, build
and browser results apply to unchanged application code; they were not rerun or
added to the new test count. No live provider or paid model was called.
Final inspection found no Ledger research containers; the same six unrelated
stopped containers were unchanged. `git diff --check` passed.

Remaining: generated regime-labelled orchestration, broader autonomous research
acceptance/real-model assessment, forward shadows and paper execution. This test
does not implement or claim those capabilities.

## Continuation: durable family development closeout (15 October)

When all allocated family work finishes, the Director atomically stores a
development disposition with the existing campaign-completion event. It records
the entry/policy hashes, candidate identity where present, structural attempt
count and reasons. Outcomes distinguish baseline-only work, manual review needed,
frozen candidate requiring validation, rejected development (abandoned under this
allocation), insufficient evidence (inconclusive), execution failure and stopped
research. No closeout grants acceptance or deployment. Explicit candidate
decisions and validation remain separate, verified workflows.

Reports verify the closeout against the saved entry and policy before showing it.
Changed evidence yields an integrity warning, not a fabricated conclusion.
Historical campaigns without a closeout are not retroactively rewritten.
Restart ticks leave completed records unchanged and do not repeat models or jobs.
This does not close a cancelled or budget-exhausted campaign as a successful
research result, and does not turn an insufficient sample into strategy rejection.

New files: `family_disposition.py`, `test_family_disposition.py` (13 unit cases).
Changed: Director completion, campaign report, director and real-Docker campaign
tests, campaign UI/browser fixture and both current-status documents. No schema
migration or trading change. Full autonomous research acceptance, regime-labelled
orchestration, forward shadows and the paper execution phase remain unfinished.

Final verification: **207 focused backend tests passed**, zero failures/skips,
199.02s with real Docker enabled. This combines the previous 194 affected tests
with the 13 closeout cases; the four real-Docker campaign paths also assert saved
closeout/report agreement. Exact suites are the simplification section's eight,
plus `test_campaign_launch`, `test_campaign_report`, `test_campaign_projects`,
`test_campaign_preparation`, `test_research_director`, `test_family_disposition`.
Log: `C:/Users/jamie/Project/research-closeout-verified-20261015.log`.
An initial numeric multi-family test exceeded its existing eight-second wait,
then passed unchanged in isolation and in the final combined run. Its timeout
and production logic were not relaxed. The interrupted combined run passed 203
checks but four Docker cases could not find the image; the allowlisted builder
restored the prerequisite before the final run. The cause of recurring tag
disappearance has not been established; this is not claimed fixed in application
code. Execution continues to fail closed without a verified image.

**135 frontend tests passed**. Production build passed (157 modules, 965.54 kB JS,
existing bundle advisory) after an identical retry cleared transient access
errors in unchanged files. Browser fixture smoke passed at **1024 / 1440 / 1920px**,
including closeout, simplification, history and validation controls, with no
runtime errors or page overflow. Isolated browser/server stopped. No full backend
suite or live/paid-provider acceptance is claimed by this focused increment.
Final Docker inspection: no Ledger research containers; the same six unrelated
stopped containers remain unchanged. Sandbox image is available as
`sha256:93ecda493ceef6a3271719226e440444d8622dd1aa5efab74148a4098544432f`.

## Continuation: automatic single-feature simplification (15 October)

New campaign policies freeze `structural_simplification=single_feature_ablation_v1`.
Before freezing a generated child, development triage now assesses the feature-off
controls already executed in Docker over the full development period and each
preregistered window at original/doubled costs. Control parameters must differ
from candidate parameters only by `research_feature_enabled=False/True`; exact
parent/control parity and prefix checks must have completed. All expected windows
must be present, in order, with finite paired expectancy. Missing evidence blocks
promotion. This uses existing reserved runs and consumes no additional data.

Exact deterministic rule: compute `child average R - parent average R` separately
for the anchor and every cost/window cell. If no difference is strictly positive,
prefer the simpler parent and reject development promotion. A positive difference
only establishes observed contribution; every existing sample-size, expectancy,
drawdown, winner-retention, cost and later validation gate still applies. No
statistical significance or combined portfolio is inferred. The existing bounded
retry policy may propose a different idea; it never activates the rejected child.

This removes **the single generated feature**, not arbitrary internal parent rules.
General multi-rule simplification and regime-labelled orchestration remain open.
Old persisted policies without this field retain their original decision structure
and behavior. No frozen strategy rules, engine accounting, source activation or
holdout permissions change. No database migration is needed. Candidate freezing
recomputes this gate through the existing evidence verifier, rather than trusting
a display-only assessment. Missing child expectancy now produces a rejection
reason instead of a `None` comparison exception exposed by the new tests.

The campaign form explains the new rule. Its report shows parent/child N and
paired expectancy differences, with an explicit limitation. New files:
`feature_ablation.py`, `test_feature_ablation.py`, `FeatureAblation.jsx`.
Changed: campaign policy and development triage, real-Docker campaign regression,
campaign UI/browser fixture, this document and the short handoff.

Verification: **138 backend tests passed** (171.09s, `LEDGER_TEST_DOCKER=1`),
including four real-Docker campaign paths: insufficient development, historical
freeze/manual validation, historical freeze/automatic validation, and new
simpler-parent rejection without holdout use. The 17 new unit cases cover verified
improvement, unchanged legacy decisions, no-benefit rejection and incomplete /
nonpaired evidence. Suites: `test_feature_ablation`, `test_research_verdict`,
`test_structural_candidates`, `test_research_campaigns`, `test_campaign_structural`,
`test_campaign_validation`, `test_generated_validation`, `test_generated_decisions`.
Log: `C:/Users/jamie/Project/feature-ablation-backend-final-20261015.log`.
An initial Docker run could not resolve `ledger-research-sandbox:v1`; rebuilding
with the existing allowlisted operator tool restored it. No fallback execution
was enabled. No live provider or paid model was called.

**135 frontend tests passed**; production build passed (157 modules, 965.11 kB JS,
existing bundle warning). Mocked browser smoke passed at **1024 / 1440 / 1920px**
with the new paired table expanded, existing history/controls working, no runtime
errors or page overflow. Isolated browser/server stopped. The complete backend
suite is still reserved for the final phase verification.
Additional launch/report/project/preparation/director compatibility suites:
**56 passed** (29.79s), log `C:/Users/jamie/Project/feature-ablation-policy-20261015.log`.
Total distinct focused backend checks: **194 passed**, zero failures/skips.
Final Docker inspection found no Ledger research containers. `git diff --check`
passed. User-owned untracked strategies and exports were preserved.

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
