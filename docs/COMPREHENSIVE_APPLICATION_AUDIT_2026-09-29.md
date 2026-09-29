# Ledger — Comprehensive Application Audit

Date: 29 September 2026  
Audited HEAD: `f98535c`  
Scope: audit only; recommendations below were not implemented as part of the audit.

This document consolidates the full audit report. Verification results describe the audited tree, not subsequent changes. Source links are relative to this document.

## A. Executive summary

**Ledger has a credible trading/research foundation, but the current tree is not release-ready.** The main weaknesses are regression control, state preservation, resource coordination and inconsistent workflow boundaries.

This audit examined HEAD **`f98535c`**. I made no application changes or fixes. Tests and browser checks used isolated data and a temporary frontend build. I did not inspect credential values or the live database.

### Verification results

| Check | Result |
|---|---|
| Full backend suite, run from `backend` | **589 passed, 20 failed**, 80.96 seconds |
| Frontend utility tests | **78 passed**, 0 failed |
| Production build | **Passed**, 118 modules |
| Production JavaScript | **823.81 kB**, 245.18 kB gzip; chunk-size warning |
| Python dependency consistency | `pip check`: passed |
| Source/documentation diff check | Passed |
| Mocked browser diagnostics/export smoke | Passed |
| Mocked experiment workflow smoke | Stopped on obsolete wording assertion |
| Journal and Portfolio page overflow | None at 1024, 1440 and 1920 px |
| Run Viewer Analysis overflow | None at those three widths |
| Live provider acceptance | Not performed |

An initial backend run from the repository root produced one additional import-test failure. Running from the documented backend directory resolved that invocation issue; **20 failures remain on the current implementation**.

### Strongest aspects

- **Trading causality is treated seriously.** Completed-bar boundaries, next-bar execution, Replay clipping, futures source-contract provenance and frozen strategy variants have explicit implementations and regression coverage.
- **Broker integration has appropriate boundaries.** Read-only adapters, account/environment identities, idempotent reconciliation and separation of execution facts from user reviews are substantive protections.
- **Research results preserve useful evidence.** Saved configurations, immutable result snapshots, setup metadata, sample counts, currency separation and conservative excursion labels support investigation.
- **The platform already has useful performance foundations.** Shared market-data storage, batched chart requests, incremental candle updates, cached frames and parent research jobs are worth retaining.
- **The shared table system is a real improvement.** Filtering, density, columns, exports and persisted preferences work across several important screens.

### Weakest aspects

- **Biggest technical concern:** recent research work broke an existing repository contract, and the regression suite is currently red.
- **Biggest UX concern:** navigation preserves presentation preferences more reliably than active work. Replay state is particularly exposed.
- **Biggest performance concern:** background data loading, nested research concurrency and repeated whole-dataset processing can compete with interactive work.
- **Biggest architectural concern:** domain responsibilities are accumulating in broadly named modules and large page components. The research repository regression demonstrates the practical cost.
- **Biggest release concern:** Git tracks a credential configuration file, installed environments and runtime output.

Throughout this report:

- **Observed** means confirmed by execution or direct implementation evidence.
- **Validation risk** means the code establishes a credible failure path, but I did not reproduce the end-user failure.

## B. Critical problems

### B1. Existing research-item storage is broken

**Problem — Observed**

The new experiment repository replaced the interface still required by the existing research-item service.

**Evidence / location**

[research_repository.py](../backend/app/storage/research_repository.py) now provides experiment `get`, `save` and `list` methods.

[research.py](../backend/app/services/research.py) still calls:

- `list_items`
- `upsert_item`
- `delete_item`

[container.py](../backend/app/services/container.py) injects that repository into the service.

The existing upsert regression fails with:

```text
AttributeError: 'ResearchRepository' object has no attribute 'upsert_item'
```

Research notes remain exposed through the Research page mounted within Charts.

**Why it matters**

This breaks an existing user workflow. It also shows that adding a new research feature can silently displace unrelated persistence behaviour.

There is no evidence here that existing database rows were deleted; the verified defect is inaccessible/broken functionality.

**Recommended solution**

Restore research-item persistence and give the two domains separate, explicit repository names. Add endpoint tests for listing, saving and deleting notes through the actual service container.

**Expected impact**

Restores functionality and prevents the same naming/coupling mistake from recurring.

**Implementation difficulty:** Low–Medium.

### B2. The repository is unsafe to treat as a clean distributable source tree

**Problem — Observed**

Git tracks:

- `backend/.env`
- **9,043 files** under `backend/.venv`
- **2,684 files** under `frontend/node_modules`
- Four runtime log files
- Python bytecode files

These paths are already listed in [.gitignore](../.gitignore), but ignore rules do not remove previously tracked files.

**Evidence / location**

Verified with `git ls-files`. Runtime logs and bytecode were already modified when inspected. No credential values were read.

**Why it matters**

- A tracked `.env` creates a credential-exposure risk.
- Tracked environments undermine reproducible installation and obscure real changes.
- Runtime logs can contain private operational information.
- Normal application use dirties the repository.
- Reviewers must distinguish source changes from machine-generated noise.

**Recommended solution**

Before distributing or publishing:

1. Review the tracked `.env` and repository history privately.
2. Rotate credentials if real secrets were committed or shared.
3. Remove generated environments, logs and bytecode from tracking while preserving local installations.
4. Keep examples and reproducible dependency manifests.
5. Verify installation and tests from a fresh checkout.

**Expected impact**

A safer release artifact, clearer reviews and reproducible development.

**Implementation difficulty:** Low for tracking cleanup; Medium if credential/history remediation is necessary.

### B3. The release verification gate is not dependable

**Problem — Observed**

The definitive backend run has **20 failures**:

| Failure group | Count | Interpretation |
|---|---:|---|
| Research-item repository regression | 1 | Functional defect |
| Research axis tests using the old signature | 18 | Tests no longer exercise the intended validation |
| Warm continuous-cache physical-read assertion | 1 | Performance-contract mismatch |

**Evidence / location**

[research_experiments.py](../backend/app/services/research_experiments.py) now requires four arguments for `axis_values`; [test_research_infrastructure.py](../backend/tests/test_research_infrastructure.py) still supplies three.

[test_research_futures.py](../backend/tests/test_research_futures.py) verifies identical bars and unchanged provider-call count successfully, then fails because the first warm request performs one physical Parquet read.

The experiment browser smoke expects “5 backtests will be run.” while the UI says “5 **exact** backtests will be run.”

**Why it matters**

A suite that is routinely red stops functioning as a regression barrier. Eighteen tests currently fail before validating their intended numeric rules.

The cache failure should not be described as incorrect futures data: the earlier equality and provider-call assertions passed.

**Recommended solution**

Restore meaningful green verification:

- Update tests to exercise the current public contract.
- Resolve whether the cache guarantee concerns provider calls, disk reads or both.
- Replace brittle wording assertions with stable semantic selectors.
- Add one documented command that runs the release checks in the correct directories.
- Require the gate before merging feature work.

**Expected impact**

Future changes become reviewable against reliable evidence.

**Implementation difficulty:** Medium.

## C. High-priority improvements

### C1. Preserve Replay sessions across navigation

**Problem — Observed implementation; loss scenario needs browser acceptance**

Replay positions, pending orders, frontier and playback state live in React component state. App navigation unmounts the page. The navigation guard checks Workspace and Journal edits, but not Replay.

**Evidence / location**

- [App.jsx](../frontend/src/app/App.jsx)
- [ReplayPanel.jsx](../frontend/src/features/strategy-lab/ReplayPanel.jsx)
- Manual checkpoint saving in `ReplayPanel.jsx`, around line 382 in the audited revision

**Why it matters**

A user can leave Replay to inspect Journal or Settings and lose an unsaved session. Closed trades may already be auto-journaled, but that does not preserve the active simulated position or pending order.

**Recommended solution**

Persist a versioned Replay session independently of the mounted page. Automatically checkpoint meaningful state transitions and provide an explicit **Resume session** workflow.

Until that exists, warn before leaving an active session and offer **Save and leave**.

**Expected impact**

Removes a significant trust and workflow-continuity problem.

**Implementation difficulty:** Medium.

### C2. “Global workers” does not represent a global simulation budget

**Problem — Observed architecture; concurrent-load impact requires measurement**

The queue limits active parent jobs. Each research parent can independently create another process pool.

**Evidence / location**

- Parent slots: [backtest_jobs.py](../backend/app/services/backtest_jobs.py)
- Child pool: [research_runner.py](../backend/app/services/research_runner.py)
- Per-pool resource calculation: [research_runtime.py](../backend/app/research_runtime.py)

For example, allowing four parents and four children per parent can permit substantially more than four simultaneous simulations, subject to each pool’s independent resource calculation.

**Why it matters**

The UI describes workers as global. Multiple experiments can compete for CPU and memory beyond that apparent limit, slowing Charts, Replay and broker work.

**Recommended solution**

Use one application-wide execution budget shared by ordinary backtests and research cells. Separate preparation slots from CPU simulation slots. Expose both requested and currently allocated capacity.

**Expected impact**

Predictable responsiveness and safer large research workloads.

**Implementation difficulty:** Medium–High.

### C3. Background cache warming can block interactive market-data requests

**Problem — Observed design; user-visible delay requires measurement**

Favourite warming defaults to two years of 1-minute history. It starts automatically from the frontend. Market-data requests share a provider-wide lock.

**Evidence / location**

- Defaults: [preferences.js](../frontend/src/app/preferences.js)
- Automatic submission: [App.jsx](../frontend/src/app/App.jsx)
- Warming: [market_warmup.py](../backend/app/services/market_warmup.py)
- Lock scope: [market_data.py](../backend/app/services/market_data.py)

**Why it matters**

Low-priority bulk history can hold the same lock needed by an interactive chart request. The automatic submission also discards its error in the app shell.

**Recommended solution**

- Prioritize interactive requests.
- Warm history in bounded chunks, releasing coordination between chunks.
- Make large initial downloads explicit.
- Show background progress, pause and failure status.
- Keep provider rate limiting distinct from cache-write locking.

**Expected impact**

Fewer unexplained chart stalls and more predictable provider usage.

**Implementation difficulty:** Medium.

### C4. Protect raw market-cache writes against interruption

**Problem — Observed non-atomic write; corruption outcome is a validation risk**

`write_bars` merges history and writes directly to the existing Parquet path. `replace_bars` already uses a temporary file followed by replacement.

**Evidence / location**

[market_store.py](../backend/app/storage/market_store.py)

**Why it matters**

An interrupted write can leave cached history unreadable. The coverage record and data file are separate pieces of state, so recovery needs an explicit policy.

**Recommended solution**

Use atomic replacement for raw cache writes as well. Add failure-injection tests around file replacement and coverage updates. Detect corrupt/missing files and invalidate coverage safely.

**Expected impact**

Stronger recovery after crashes, forced shutdowns and disk failures.

**Implementation difficulty:** Medium.

### C5. Validate adjusted-history consistency after corporate actions

**Problem — Validation risk**

Alpaca history defaults to split adjustment. Existing cached history is retained while missing date ranges are appended. The namespace identifies the adjustment mode, but not its revision/vintage.

**Evidence / location**

- [alpaca.py](../backend/app/data/providers/alpaca.py)
- [market_data.py](../backend/app/services/market_data.py)
- [market_store.py](../backend/app/storage/market_store.py)

**Why it matters**

If a split changes the provider’s historical adjusted series, an old cached segment and a newly fetched segment may represent different adjustment bases.

I did not reproduce this against a real split.

**Recommended solution**

First add a deterministic provider fixture that revises historical prices and volume after a split. Then define a revision/invalidation policy and persist the relevant data identity in saved runs.

**Expected impact**

Prevents artificial discontinuities from contaminating indicators, stops and research results.

**Implementation difficulty:** Medium.

### C6. Journal filtering repeatedly loads and processes the entire journal

**Problem — Observed**

The repository selects all trades, converts them, then filters in Python. Frontend search changes request a new report without debounce or request cancellation.

**Evidence / location**

- [journal_repository.py](../backend/app/storage/journal_repository.py)
- [useJournalData.js](../frontend/src/features/journal/useJournalData.js)
- [JournalPage.jsx](../frontend/src/features/journal/JournalPage.jsx)

**Why it matters**

As imports accumulate, typing can trigger repeated full-journal scans, analytics and response serialization. Ignoring an obsolete response prevents stale display but does not stop the wasted backend work.

**Recommended solution**

- Debounce text input and cancel obsolete requests.
- Push supported filters and sorting into SQL.
- Return paginated rows separately from matching-subset aggregates.
- Preserve existing OR-within-field, AND-across-field and currency semantics.

**Expected impact**

A materially more responsive Journal at larger sizes.

**Implementation difficulty:** Medium–High.

### C7. Research polling transfers too much immutable data

**Problem — Observed**

The jobs endpoint returns up to 500 full job payloads every polling cycle. Research parents contain child configurations. The experiment viewer fetches saved runs while progress changes and through its own polling loop.

**Evidence / location**

- [backtest_jobs.py](../backend/app/services/backtest_jobs.py)
- [useBacktestJobs.js](../frontend/src/features/strategy-lab/useBacktestJobs.js)
- [ResearchExperimentViewer.jsx](../frontend/src/features/strategy-lab/ResearchExperimentViewer.jsx)
- [research_experiments.py](../backend/app/services/research_experiments.py)

**Why it matters**

Most of this information does not change between polls. Repeatedly decoding configurations and complete results makes research monitoring progressively more expensive.

**Recommended solution**

Return compact job status and cell-metric summaries. Fetch configurations and full trade/equity data on demand. Consolidate polling and stop it when no active work needs monitoring.

**Expected impact**

Less network traffic, JSON parsing and UI work while experiments run.

**Implementation difficulty:** Medium.

### C8. Failures are sanitized into messages too vague to diagnose

**Problem — Observed**

Broker scheduling, research workers and backtest jobs often discard the original failure classification. Some loops swallow exceptions entirely.

**Evidence / location**

- [broker_scheduler.py](../backend/app/services/broker_scheduler.py)
- [backtest_jobs.py](../backend/app/services/backtest_jobs.py)
- [research_runtime.py](../backend/app/research_runtime.py)

**Why it matters**

“Check strategy, dates, provider configuration and data availability” gives the user several unrelated possibilities without identifying the actual problem.

Credential protection is appropriate; losing all diagnostic information is unnecessary.

**Recommended solution**

Introduce sanitized error categories and correlation IDs:

- Authentication/configuration
- Entitlement
- Rate limit and retry time
- Missing history
- Invalid strategy parameters
- Strategy failure
- Storage failure
- Worker termination

Retain safe local diagnostic details without raw tokens, URLs or arbitrary plugin exception text.

**Expected impact**

Faster recovery and much less trial-and-error troubleshooting.

**Implementation difficulty:** Medium.

### C9. Uploaded “images” are not validated as images

**Problem — Observed validation gap; exploitation not tested**

The attachment endpoint accepts any client-supplied content type starting with `image/`, preserves a filename suffix and copies the content without an explicit application size limit. Files are served through the backend’s static upload mount.

**Evidence / location**

- [journal.py](../backend/app/api/journal.py)
- [main.py](../backend/app/main.py)

**Why it matters**

The content-type header is not evidence that the bytes are an image. Active content or oversized files can enter a trusted local application through attachments.

This is not evidence of an internet-exposed compromise; Ledger’s documented deployment remains local.

**Recommended solution**

Allow specific raster formats, validate/decode their bytes, constrain size and dimensions, and serve unsupported content as downloads. Add rollback/cleanup for failed database persistence after a file write.

**Expected impact**

A tighter trust boundary and fewer malformed-file failures.

**Implementation difficulty:** Medium.

## D. Medium-priority improvements

| Finding | Evidence and impact | Recommended change |
|---|---|---|
| Navigation is state-based, not URL-based | [App.jsx](../frontend/src/app/App.jsx) persists a page name but not a navigable run/session URL. Back/forward, bookmarks and reproducible handoffs are limited. | Add routes incrementally, beginning with saved runs and experiments. |
| Eager page loading | All major pages are imported by App; production JS is 823.81 kB. | Lazy-load Backtest, Replay, Journal, Portfolio and Workspace boundaries. |
| Portfolio and Screener pagination is mostly cosmetic | [usePortfolioSnapshot.js](../frontend/src/features/portfolio/usePortfolioSnapshot.js) and [useScan.js](../frontend/src/features/screener/useScan.js) fetch every server page before client presentation. | Server-side pagination/filtering with separately computed summaries and explicit full exports. |
| Replay volume and overlays still do bulk work | [ReplayChart.jsx](../frontend/src/features/strategy-lab/ReplayChart.jsx) incrementally updates candles but replaces volume data. Overlay effects remove/recreate series. | Reconcile series by stable identity; append/update points when possible. |
| Crosshair movement updates React state on every event | [PriceChart.jsx](../frontend/src/features/research/PriceChart.jsx), ReplayChart. | Update a small readout independently and skip unchanged candle values. Measure before restructuring the chart. |
| Repeated session preparation remains expensive | [intraday_baselines.py](../backend/app/backtesting/strategies/intraday_baselines.py) converts timestamps and validates a growing session repeatedly. | Precompute immutable session indexes/validity without changing frozen strategy rules. |
| Research diagnostics repeatedly rebuild historical slices | [orb_participation.py](../backend/app/backtesting/strategies/orb_participation.py). | Cache causal daily/minute reference statistics with future-append invariance tests. |
| Settings overstates persistence/freshness | Automatic favourite warming is browser-triggered; market cache coverage is not a guarantee that historical bars will never be revised. | Describe scope accurately and distinguish downloaded coverage, freshness and validation status. |
| Daily Review silently falls back to `Main` | [JournalPage.jsx](../frontend/src/features/journal/JournalPage.jsx) chooses `Main` for ambiguous multi-account days. | Ask for an account or open a clearly labelled all-account summary before creating a review. |
| SQL connection lifetime is implicit | `with database.connect()` commits/rolls back but does not itself explicitly close a SQLite connection. | Provide a connection context helper that closes deterministically; measure handle growth under polling. |
| Migrations run broad initialization work | [database.py](../backend/app/storage/database.py) reruns migration inspection and a journal update. | Keep compatibility, but use explicit versioned migration execution and restoration tests. |
| Documentation has broken entry points | README links to missing CP12, AGENTS and workflow files; release index links to missing CP12. | Repair the current documentation map and remove stale milestone claims. |
| Python dependencies are unpinned | [requirements.txt](../backend/requirements.txt), requirements-dev. | Record a tested dependency set and verify fresh installation. |
| Duplicate table implementation remains | `components/DataTable.jsx` duplicates the active `components/table/DataTable.jsx`; no current import was found for the old path. | Complete reference/dynamic-loading checks, then remove or explicitly deprecate it. |

### Data and quantitative limitations

These should remain visible limitations, not be hidden behind polished result screens:

- **Current-universe screening is not point-in-time universe reconstruction.**
- Historical stock-universe research remains exposed to survivorship bias.
- Current SEC/fundamental snapshots should not be treated as historical information available at an earlier decision date.
- Cached OHLCV and saved results do not automatically constitute a fully reproducible data/code archive.
- Intrabar price ordering cannot be recovered from OHLC alone. The deterministic same-bar policy and excursion lower-bound labels should remain explicit.
- Zero commission/slippage defaults can be useful for diagnostics, but should be labelled prominently as cost assumptions.
- Strategy warmup consumes available history. Ordinary runs need a clearer distinction between requested dates, warmup dates and first eligible trading date.
- NQ provider entitlement, live coverage and TradingView parity were not established by this audit.

I did not find evidence in the inspected paths that justifies changing frozen Gold, Momentum, ORB or VWAP rules.

## E. Small improvements / polish

1. **Make source and account scope persistent in Portfolio.** The inspected screen has a page-level account control, a separate broker account control and manual holdings further down. Their scopes are easy to confuse.

2. **Remove repeated sample-count text.** Portfolio displays both `N = 35` and a second matching-record summary immediately below.

3. **Hide row selection where it has no available action.** A checkbox column implies a meaningful bulk workflow.

4. **Use clearer research terminology.** “Research” means Screener in top navigation, company research inside Charts and experiments inside Backtest.

5. **Move explanatory paragraphs into contextual help.** Backtest, Replay and Portfolio repeatedly explain internal contracts before the user reaches the action.

6. **Label timestamps consistently.** Show data “as of,” timezone and stale status together.

7. **Improve modal keyboard behaviour.** Table popovers have Escape handling and focus restoration, but need a deliberate focus-containment policy. Test keyboard-only operation rather than relying on `role="dialog"`.

8. **Clarify unavailable values.** Differentiate “not supplied by provider,” “not yet synced,” “no sample” and “request failed.”

9. **Keep success feedback near the action.** Saving a review, queuing research and warming data should have visible, local confirmation.

10. **Repair the missing favicon request.** The isolated production server returned a favicon 404.

## F. Performance improvement plan

Do this in measured order.

| Order | Work | Measurement and acceptance |
|---|---|---|
| 1 | Establish repeatable fixtures and traces | Record cold/warm provider calls, disk reads, preparation, simulation, persistence, peak memory and UI request latency. |
| 2 | Fix global scheduling and interactive priority | Run two research experiments alongside Charts/Replay. Verify actual child count, memory and interactive p95 latency stay within the selected budget. |
| 3 | Reduce polling payloads | Measure response bytes and frontend JSON/render time with 500 jobs and a populated 64-cell experiment. |
| 4 | Scale Journal filtering | Benchmark 1k, 10k and 100k trades. Track SQL time, aggregate time, response size and typing-to-result delay. |
| 5 | Remove redundant chart work | Capture browser traces during crosshair movement, panning and Replay at multiple speeds. Count full `setData`, series recreation and long tasks. |
| 6 | Optimize causal session preparation | Profile the current implementation on fixed synthetic and real cached windows. Require identical setup/trade/equity outputs. |
| 7 | Lazy-load major pages | Compare transferred JS, parse time and first usable screen on cold navigation. |
| 8 | Reduce whole-history cache rewrites | Measure read/write bytes and elapsed time for a one-day append to multi-year history before choosing partitioning. |

**Important distinction:** the current build size and failing cache-read assertion are measured. Current browser frame rates and six-month research speedups were not measured in this audit.

Do not begin with GPU work, a chart-library replacement or broad DataFrame rewrites. None is justified by the evidence gathered here.

## G. UI / UX redesign recommendations

### Keep the top navigation; improve the hierarchy beneath it

The compact top navigation and full-width shell are useful. Another wholesale navigation redesign would spend effort without addressing the main friction.

A clearer hierarchy would be:

| Area | Recommended internal structure |
|---|---|
| Overview | Trading, Investments, Active work, Recent activity |
| Charts | Chart workspace, Instrument details/notes |
| Replay | Session, Orders/position, Session history |
| Backtest | Configure, Runs, Experiments, Strategies/Workspace |
| Journal | Trades, Analysis, Calendar, Daily Review, Playbook |
| Portfolio | Account/source selector, Positions, Activity |
| Screener | Saved scans, Results, Coverage |
| Settings | Appearance, Trading defaults, Providers, Data/maintenance |

Rename the current top-level “Research” to **Screener** unless it becomes a genuine home for all research workflows.

### Backtest: separate configuration, execution and investigation

The current page exposes a long sequence of configuration, ready summary, compute controls and expandable research tools. The concepts are valid, but their hierarchy is weak.

Replace this with:

- A compact top section: strategy, symbols and dates.
- A second section: account sizing and essential strategy inputs.
- Collapsed advanced execution/cost settings.
- A concise ready summary directly beside the primary action.
- A small active-jobs strip.
- Separate saved-run and experiment investigation screens.

Keep validation and spectrum/grid tools secondary, but make **Experiments** a discoverable destination rather than something users must rediscover inside configuration.

### Replay: make the active session the primary object

Use:

- Header: instrument, simulated time, session name, saved status.
- Main workspace: chart.
- Stable compact order/position panel.
- Playback controls adjacent to the chart.
- Collapsed setup and indicator management.
- Explicit **Save**, **Resume**, **End session**.

Leaving the page should not implicitly end a session.

### Portfolio: one scope selector before any metrics

The browser inspection showed two independent account scopes and broker/manual content stacked vertically.

Replace that with:

```text
Portfolio
[Source: Trading 212 / Manual] [Account] [As of / Sync state] [Sync now]

Account metrics

Positions | Orders & fills | Cash | Dividends
```

Show the manual transaction workflow only when Manual is selected. Preserve the distinction between broker facts and locally reconstructed holdings.

The screenshot also showed tiny table text combined with relatively tall compact rows. Tighten vertical padding before reducing typography further. The existing nested page/table scroll should be used deliberately, not on every short table.

### Journal: preserve the shared filter model, improve review flow

- Keep compact search, filter chips and header filtering.
- Make **Review next unreviewed trade** a primary workflow.
- Use a detail drawer that retains table position.
- Show account/timezone/date basis together.
- Require account selection when a Calendar day is ambiguous.
- Keep filtered summaries visible without repeating every statistic.

### Settings: replace one long form with task-based sections

The current Settings implementation renders many groups together.

Use secondary tabs:

- Appearance
- Charts & Replay
- Backtest defaults
- Providers & broker sync
- Data cache
- Maintenance

Provider sections should explain capability, readiness, last success and next action. “Configured” alone does not prove entitlement or usable history.

### Workflow interaction review

These are control-path estimates, not timed usability measurements.

| Workflow | Current interaction pattern | Improvement |
|---|---|---|
| Launch after setup | One launcher action | Preserve; add a precise readiness/error screen rather than only port readiness. |
| Change chart timeframe | One control action | Preserve; show loading while retaining the previous chart context. |
| Start Replay | Navigation, instrument/date setup, load: roughly 4–6 actions | Remember named sessions; resume in one action. |
| Re-run a saved configuration | Runs, row menu, use settings, run: roughly 4 actions | Offer “Re-run” with explicit current-data versus original-snapshot semantics. |
| Review a trade | Journal, trade, edit, save: roughly 3–4 actions | Keep drawer open and advance to next unreviewed trade. |
| Compare runs | Select at least two rows, inspect comparison | Add a stable comparison URL and saved selection. |
| Change broker setup | Leave workflow, locate Settings group, edit external configuration where required | Provide contextual links to the exact provider section. |
| Investigate an experiment | Find it under Runs, open viewer, open cell/run | Add direct experiment links and retain viewer state on return. |

## H. Architecture improvement plan

### 1. Separate domains before extracting more generic infrastructure

The repository regression came from two different concepts sharing “ResearchRepository.”

Use explicit ownership:

- Research notes/items
- Research experiments
- Saved backtest runs
- Queue jobs

Do not solve this by making one larger repository support everything indefinitely.

### 2. Introduce typed boundary contracts

The frontend API client and backend responses exchange substantial loosely structured dictionaries.

Start with the highest-risk contracts:

- Job summary
- Experiment summary/cell result
- Saved-run identity
- Broker snapshot
- Journal report
- Replay session

Runtime/schema validation at boundaries would catch more valuable defects than converting every component at once.

### 3. Separate session state from page rendering

Move Replay session state and Backtest draft configuration into dedicated controllers. Page components should render and dispatch actions.

The roughly 500-line Replay component mixes:

- Fetching
- Playback
- Order handling
- Position transitions
- Journaling
- Checkpoints
- Drawings
- Indicator requests
- Presentation

Extract by responsibility with behaviour-preserving tests.

### 4. Introduce a shared job resource coordinator

Keep the existing queue and parent experiment model. Replace independent capacity decisions with one allocator.

There is no demonstrated need for an external distributed queue for Ledger’s current local deployment.

### 5. Make persistence and data provenance explicit

For each saved run, record consistently:

- Strategy version/source identity
- Effective parameters
- Engine/application version
- Data identity and adjustment mode
- Requested versus actual dates
- Warmup coverage
- Provider/source contracts
- Execution/cost assumptions

Research already has parts of this. Ordinary runs should follow the same contract.

### 6. Reduce CSS override layering incrementally

[styles/index.css](../frontend/src/styles/index.css) overrides utility classes under `.dense-page`, including padding and margin utilities.

That makes a component’s declared classes less predictive.

Move repeated layout rules into explicit primitives and tokens when touching those components. Do not rewrite the stylesheet wholesale.

### 7. Keep local trust boundaries explicit

Workspace runs trusted Python; strategy discovery imports modules. Those are intentional extension mechanisms, not sandboxes.

Maintain that limitation. If remote or multi-user deployment becomes a real requirement, authentication, process isolation, origins and file access need a separate design phase.

## I. Testing improvement plan

### What is already tested well

The current suite provides substantial coverage for:

- Frozen strategy behaviour
- Engine execution and accounting
- Replay causality
- Futures provenance and rolls
- Broker identities and reconciliation
- Journal preservation and filtering
- Research parent recovery/cancellation
- Table models, exports and preference persistence

The passing tests are useful evidence. They are not a substitute for current provider acceptance or browser integration.

### Highest-value additions

1. **Actual API contract tests for research notes and experiments.**  
   The existing failure demonstrates why service-container wiring matters.

2. **Replay navigation/reload recovery.**  
   Cover active position, pending order, closed unsaved trade, frontier and drawing state.

3. **Multiple simultaneous research parents.**  
   Assert a real global child-process limit and cancellation behaviour.

4. **Cache crash recovery.**  
   Fail before/after file replacement and coverage updates.

5. **Corporate-action cache revision.**  
   Simulate a split after older adjusted history has been cached.

6. **Large-journal performance and aggregate consistency.**  
   Ensure paginated rows and summaries describe the same filtered population.

7. **Provider contract fixtures.**  
   Include pagination, partial responses, malformed records, rate limits and entitlement failures.

8. **Attachment validation.**  
   MIME mismatch, active content, excessive dimensions/size and persistence rollback.

9. **Full research browser workflow against an isolated real backend.**  
   Mocked fetch proves frontend behaviour but cannot catch the broken repository wiring.

10. **Keyboard and focus acceptance.**  
    Table filters, row menus, drawers, modals and navigation.

11. **Fresh-checkout installation and release build.**  
    Especially important once tracked environments are removed.

12. **Session-calendar edge cases.**  
    Half-days, DST transitions, missing opening minutes and futures session boundaries.

### Commands run

From `backend`:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider `
  --basetemp C:/Users/jamie/Project/audit-pytest-backend-sept29 --tb=short
```

Result: **589 passed, 20 failed, one warning**.

From repository root:

```powershell
node --test frontend/tests/*.test.js
```

Result: **78 passed**.

Production build used the current source and an external output directory. From `frontend`:

```powershell
node node_modules/vite/bin/vite.js build --configLoader runner `
  --outDir C:/Users/jamie/Project/audit-ledger-build-sept29
```

Result: **passed**. An initial sandbox-only import-resolution failure disappeared when the same build ran outside that restriction; it was not classified as an application defect.

### Browser evidence and limits

Passed on the current production bundle with intercepted API responses:

- All 16 ORB diagnostic bucket choices
- Scalar diagnostic CSV fields
- Full versus filtered Run Viewer exports
- Immutable full-run JSON export
- Journal notes/review export preservation
- Portfolio holdings, transactions and broker activity exports
- Account separation in exports
- No runtime exceptions in that smoke

No page-level overflow was found in the checked Journal, Portfolio and Run Viewer Analysis views at **1024, 1440 and 1920 px**.

I did **not** complete current live-provider chart/Replay acceptance, realistic chart-load profiling, or every screen’s browser workflow. The experiment smoke needs maintenance before it can supply reliable full-flow evidence.

## J. Quick wins

Recommended low-risk starting work:

1. Restore the research-item repository contract.
2. Repair the 18 stale axis tests and obsolete browser assertion.
3. Correct the cache test’s intended guarantee.
4. Remove generated files from Git tracking after private secret review.
5. Repair the four broken documentation links.
6. Add frontend `test` and complete verification scripts.
7. Add a Replay leave warning while proper session persistence is developed.
8. Stop idle job polling and omit child configurations from status responses.
9. Debounce Journal text search.
10. Rename top-level Research to Screener.
11. Remove duplicate sample-count text.
12. Add structured failure categories without exposing raw exceptions.

## K. Long-term improvements

### Small quality-of-life capabilities

- Resume last Replay session
- Review next unreviewed Journal trade
- Direct links to runs, experiments and provider settings
- Saved comparison selections
- Clear data freshness and missing-history indicators
- Keyboard shortcuts discoverable from one help panel

These reduce repetition in workflows Ledger already supports.

### Medium improvements

- Versioned, exportable research manifests
- Managed backup and verified restore
- Data-quality reporting for gaps, adjustments and session coverage
- Shared request cancellation/caching conventions
- Resource-aware job scheduling
- Durable named Replay sessions
- Server-side table querying with consistent exports

These improve confidence and scale without adding unrelated trading features.

### Major future capabilities

- **Point-in-time universe support**, if universe-wide historical research becomes a serious objective.
- **Explicit portfolio research rules**, if independent per-symbol batches are to become portfolio conclusions.
- **Historical data snapshot management**, for reproducibility across provider revisions.
- **Remote/multi-user deployment**, only with a deliberate security and process-isolation model.

None should precede restoring the current release gate.

## L. Recommended implementation order

### Phase 1 — Restore release integrity

- Fix research-item storage.
- Repair stale tests and browser selectors.
- Resolve the warm-cache performance contract.
- Review tracked credentials and remove generated artifacts from tracking.
- Repair documentation entry points.
- Verify a fresh installation.

**Exit condition:** meaningful green backend/frontend/build verification from a clean checkout.

### Phase 2 — Protect work and persisted data

- Preserve Replay sessions across navigation/reload.
- Make raw Parquet writes atomic.
- Add cache interruption and corporate-action revision tests.
- Validate attachments.
- Introduce sanitized error categories.

**Exit condition:** common navigation, process interruption and malformed-input scenarios have explicit recovery behaviour.

### Phase 3 — Control resource usage and latency

- Enforce one global simulation budget.
- Prioritize interactive data requests over bulk warming.
- Reduce queue/experiment polling payloads.
- Debounce and paginate Journal queries.
- Establish repeatable performance benchmarks.

**Exit condition:** research workloads do not unpredictably degrade ordinary interaction.

### Phase 4 — Improve workflow coherence

- Add URL-backed runs/experiments.
- Reorganize Backtest configuration versus investigation.
- Unify Portfolio scope controls.
- Clarify Screener/research naming.
- Split Settings into task-based sections.
- Improve Journal review-next and account selection.

**Exit condition:** ordinary workflows require fewer repeated inputs and retain context.

### Phase 5 — Target measured chart and simulation bottlenecks

- Incremental Replay volume/overlay updates.
- Isolated crosshair readouts.
- Causal session/diagnostic precomputation.
- Lazy-loaded page bundles.
- Storage partitioning only if measured append costs justify it.

**Exit condition:** measured improvement with identical trading outputs.

### Phase 6 — Consolidate maintainability and polish

- Extract Replay and Backtest controllers.
- Standardize boundary contracts.
- Remove verified dead implementations.
- Replace fragile CSS overrides incrementally.
- Complete keyboard, viewport and empty/error-state acceptance.

**Recommendation:** pause feature expansion until Phases 1 and 2 are complete. Ledger’s next gains should come from dependable existing workflows and trustworthy verification, rather than additional strategy or UI breadth.
