# Research lifecycle diagnostics

This extends the [24 October failure repair](RESEARCH_DIAGNOSTICS_2026-10-24.md).
It does not retry old campaigns or authorize paid requests.

## Access

Set `RESEARCH_DIAGNOSTICS_TOKEN` in the backend environment to a private random
token of at least 32 characters. Keep it separate from provider keys and MT5
bridge tokens. The committed `.env.example` contains an empty placeholder only.
Apply the environment change at a planned backend restart, after active work has
finished. No backend restart or production configuration change is performed by
the development tests.

On Research Agent, expand **Research lifecycle diagnostics**, enter that token,
and select **Connect diagnostics**. The token is held in component memory only;
reload, navigation away or disconnect requires entering it again. It is sent in
an Authorization header, never in a URL, copied report, localStorage or sessionStorage.
Do not send this token over an untrusted cleartext network.

The new endpoint is `GET /api/strategy-lab/research-campaigns/{id}/diagnostics`.
It accepts `after` (exclusive sequence) and `limit` (1–100). Unconfigured access
returns 503; missing/wrong credentials return 401. Successful responses are
`Cache-Control: no-store`. Read operations do not initialize schemas or dispatch work.
The token authorizes local operator access across campaigns, not multi-user tenancy.
**Other existing Ledger API routes are not secured by this token.**

## Persistence and scope

`agent_diagnostics` is an additive SQLite table with an AUTOINCREMENT sequence,
campaign index, sanitized public JSON and a separate private exception-frame field.
Events are written in the same transaction as the associated state transition.
An event-write failure rolls back that transaction instead of inventing success.
No existing campaign, run, holdout, Journal record or broker cursor is rewritten.

Retention is capped at 1,000 events per campaign and 10,000 globally. Sequences
are never reused. The reader reports possible retention gaps; gaps may also reflect
interleaved events from other campaigns. The frontend retains at most 200 events,
fetching one bounded page per existing campaign refresh. There is no extra timer.

Hooks cover campaign/history actions, Committee/Code Author state and validation
stages, research-owned backtest job state changes, numeric-loop state changes and
Docker phase/status changes. No per-bar diagnostics are appended. Current progress
and suspected stalls remain available from the existing bounded monitoring panels.
Legacy failure explanations remain available without backfilling invented events.

Exact model stages distinguish request, usage, authorization, schema, evidence,
parameter proposal, preregistration and source validation where reached. Stable
codes include evidence mismatch, model rate limit/authentication/refusal/incomplete
output, budget/usage/authority/deadline failure, history missing/incomplete,
strategy incompatibility, backtest failure and sandbox failure. Unknown exception
text is never used as a public diagnostic.

Private exception chains contain class names and bounded frame file basenames,
function names and line numbers. They exclude full paths, source lines, locals,
exception arguments, prompts, model output, source archives and holdout values.
These private fields are never selected by the event API. They are diagnostic
records, not a complete raw Python traceback dump.

In development builds, opt-in F12 output groups INFO/WARNING/ERROR events and
deduplicates ordinary polling. Copy event diagnostics includes campaign identity
and public event details only.

## Discovery behavior

Automatic discovery records incompatible families in `rejected_families` and
continues independent compatible catalog entries without substitutions or spending
on rejected entries. A specifically selected incompatible strategy still fails.
Families outside the requested catalog count are not checked or substituted.
Both cached and provider-preparation paths preserve the rejection information.

## Limits still requiring work

- No recovery of lost historical provider exceptions or rejected response text.
- Database outages can prevent durable event storage. The coordinator now records
  sanitized failure frames independently in `research-private/coordinator-failures.jsonl`
  beside the database (256 KiB plus two backups, one backend coordinator owner).
  This operator-only fallback excludes exception messages and provider output,
  is not exposed through HTTP, and never claims a state transition committed.
  If the filesystem also fails, logging is best-effort and the original bounded
  three-failure stop remains authoritative. POSIX files/directories use 0600/0700;
  Windows additionally relies on the data directory's existing user ACL.
- Not every fine-grained numerical/evaluation gate has a dedicated event/code.
  Some worker failures still require the linked job and private frame record.
- No new background retry, model spending, holdout access, deployment or execution
  permission is granted by this feature.
- The authenticated frontend acceptance uses mocked HTTP responses; backend
  authentication/persistence tests use real API handlers with temporary databases.

Verification results are recorded in the current unified development handoff.

Verified lifecycle checkpoint: backend 2,065 passed / 41 skipped (601.86s), frontend 145 passed, production build passed, browser 390/1024/1440/1920 including authenticated-reader fixtures, token non-persistence and reload passed. Existing deprecation/chunk-size warnings remain. No paid calls or production DB changes.
