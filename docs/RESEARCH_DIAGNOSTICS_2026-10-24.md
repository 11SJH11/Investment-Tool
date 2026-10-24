# Research Agent failure investigation — 24 October 2026

## Scope and status

This is the first repair checkpoint, **not completion of the full diagnostics brief**.
Prior work is preserved in commit `526838a` (acceptance spending and MT5 clock observations).
No paid model calls, campaign retries, broker orders or production database writes were performed for this investigation.

## Saved campaign evidence

Campaign `6f78e397-ec40-4a61-accb-9c569329e90a`, created
`2026-10-24T16:00:14.489112+00:00`, was inspected through read-only SQLite.
The persisted internal state is `DEVELOPMENT_COMPLETE`; its entries are
`RESEARCH_STOPPED` and `FAILED`. The existing presentation correctly reports failure,
not successful research merely because the coordinator is alive.

### Opening range

The actual request used XAUUSD, primary 1m, automatic session, no extra timeframes,
empty strategy parameters, development 2023-08-13 through 2025-11-04 and warmup
beginning 2022-10-21. Account settings were $10,000, risk_pct 1%, max leverage 100,
five maximum open positions, stop-first, overnight allowed, no weekday override,
and zero commission/spread/slippage. These are recorded assumptions, not broker costs.

The selected key was `opening_range_breakout_research_v1`, class `OpeningRangeResearch`
in `intraday_baselines`, source SHA-256
`244560f47921d0543d6ef1c43997a32d5181f660b9f2a3ea8525e279b29d7353`.
Its existing market validator rejects spot metals: it requires one-minute equities
or supported futures with traded volume. BacktestService calls that validator
before loading historical prices. The same submitted market combination is now
covered by a deterministic regression test. Cached history was recorded under
`oanda-mid-v1`; the incompatible strategy does not become valid because this cache exists.

The original failed queue job is no longer present in the inspected jobs table.
Consequently the original exception/traceback cannot be recovered from that table.
The persisted campaign records `baseline_stopped_or_failed`, and the screenshot
records `invalid_parameters`. The incompatible configuration is confirmed; a
claim to have recovered its original traceback would be incorrect.

### Committee and Code Author

Both saved review records have `error=unknown_evidence_reference`, empty accepted
roles and a Researcher operation marked RETURNED:

| Operation | Input/output tokens | Returned at UTC |
| --- | --- | --- |
| Committee `2724d642-1f65-4be7-b866-2cfee4018b7c` | 1733 / 329 | 16:32:46.901596 |
| Code Author `fe42bd3b-229b-4d52-9f33-f6c355406e83` | 10922 / 263 | 17:04:14.991670 |

Both stopped at exact evidence-map membership validation after schema parsing,
usage checks and post-call authority checks. No accepted Researcher proposal,
numeric trial, CodeAuthor source generation or Docker child followed these failures.
The invalid reference strings were not persisted: their exact spelling is unknown.
Do not infer that an axis, source validator, Docker, budget or provider transport
caused these particular failures. Stored cost estimates used the campaign pricing
snapshot and are not an invoice or confirmation of current pricing.

## Implemented repair

- Research discovery and director dispatch now check the existing ORB/VWAP market
  restriction before simulations/model allocation. No frozen strategy rule changes.
- Preparation exposes `strategy_instrument_unsupported` with a corrective message.
  This initial repair rejects an incompatible selection conservatively; it does
  not yet partition a mixed selection into independent accepted/rejected families.
- The OpenAI structured-output schema constrains evidence references to an enum
  of the supplied evidence-map keys. Exact server-side validation remains mandatory.
  There is no fuzzy matching, automatic citation repair or paid retry.
- Committee and author persist a bounded validation diagnostic on rejection,
  including stage, role, UTC time and counts. Untrusted rejected references are
  represented by hashes, never raw response text, paths or credentials.
- Existing read-only campaign polling returns a separately allowlisted diagnostic.
  Legacy failures are explained without modifying their records or fabricating details.
- Research Agent displays expandable failures and Copy diagnostics. Development
  builds offer opt-in F12 output, deduplicated during ordinary polling. No new timer.
  A reload obtains failures again from persisted backend records.
- No schema migration is required: new failure details use existing review JSON.

## Remaining diagnostics work (next priority)

1. Durable append-only, bounded lifecycle events with sequence/correlation/parent IDs
   across preparation, jobs, numeric research, models, Docker, evaluation and storage.
2. Authenticated incremental read-only event API. Existing campaign routes currently
   have no application authentication dependency; this checkpoint does **not** claim
   the existing polling endpoint is authenticated or safe to expose publicly.
3. Safe private tracebacks/causal chains and stable categories for failures beyond
   unknown evidence references; retention and write-failure behavior.
4. Validate the remaining strategy contracts, parameters, data and family-level
   rejection/continuation before campaign allocation. No silent substitution.
5. Expand console/panel coverage and tests to all requested failure/stall categories;
   cursor reconnect/dedup and real-backend browser acceptance remain outstanding.

After this priority: resume Research Agent genuine acceptance (paid calls remain
on hold), MT5 timing/protection/recovery, Algo Trading monitoring and annotations.
Future demo permission does not bypass account identity or timing safety gates.

## Verification

- Focused backend: 52 passed, 1 skipped (22.19s), one existing Starlette warning.
- Frontend: 145 passed.
- Production build passed, 179 modules; existing large-chunk warning. A Windows
  extension-resolution collision was fixed with an explicit component `.jsx` import.
- Mocked browser smoke passed at 390/1024/1440/1920: GET-only, reload, error panel,
  existing progress/activity, no runtime errors or page overflow. This is not a
  genuine model call or live backend/browser end-to-end acceptance.
- Full backend: **2,059 passed, 41 skipped**, one existing Starlette/httpx
  deprecation warning, 623.82 seconds. `git diff --check` passed.

User-created `experimental_strategy_batch_2026_v1.py` and run-220 through run-230
exports are unrelated and must remain unstaged/preserved.
