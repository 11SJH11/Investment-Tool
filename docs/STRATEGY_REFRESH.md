# Manual strategy refresh

Normal workflow: add/edit a trusted Python module in `backend/app/backtesting/strategies`,
open Backtest > Strategies > Refresh strategies, then select it in Backtest.
Underscore-prefixed drafts and base/registry infrastructure remain excluded. No
filesystem watcher, upload API, automatic refresh or application restart is involved.
The normal frontend no longer mounts Workspace; its backend, drafts and history
are retained. Saved Workspace results remain readable, but their settings are not
silently rerun against a different ordinary strategy.

## Loading and failures

`POST /api/strategy-lab/strategies/refresh` rescans local top-level Python modules,
invalidates import caches and compiles captured source bytes, bypassing stale pyc
files. Modules load into fresh namespaces. The existing registry publishes a new
mapping only after the complete candidate set validates. This is one registry with
an atomic update, not a second plugin system.

Syntax/import/duplicate/spec/interface/constructor failures return module-specific
errors and `ok=false`; existing registry classes and module references are restored.
The UI retains its old list on failure and shows the error. Successful responses
include the new list and added/updated/removed counts. Updated counts compare each
strategy's own module hash; helper changes are represented by the registry hash.
Removing a source file removes its strategies only on a successful refresh.

This remains trusted local Python, not a sandbox. Arbitrary module side effects
cannot be undone; do not load untrusted plugins. Strategy packages/dynamic imports
outside the discovered top-level modules are not a new supported plugin mechanism.

## Active jobs and reproducibility

Refresh returns HTTP 409 while any direct backtest, preparation or queued/research
worker execution is active. It does not wait for a long job, cancel it, mutate its
module globals or restart Ledger. Retry manually when active work finishes.
Queued jobs which have not started may use the refreshed generation.

Research workers receive the parent's captured strategy sources in the existing
private temporary input snapshot. Later filesystem edits do not substitute new
code into research cells. Prepared inputs also carry provenance and reject a
mismatched registry generation. Research retries reject mixing implementation hashes.

Future results and saved configurations include strategy key, module, class, source
SHA-256 and a discovered-module manifest SHA-256. The Run Viewer displays the saved
source hash; older results explicitly say no source fingerprint was recorded.
Saved results are not recalculated or migrated by refresh. This identifies source
versions; it is not a permanent source archive or a guarantee of identical external
libraries/data. Built-in strategy rules and engine fill/accounting logic are unchanged.

## Acceptance

Deterministic tests cover discovery, same-size edits, old-instance isolation,
syntax/import/spec/signature failures, duplicate keys, active-execution refusal,
API list/error responses, immutable saved results and captured worker source.
Frontend tests cover list/parameter reconciliation, errors and legacy Workspace
navigation fallback.

Verified on 2026-10-04: focused backend checks 31 passed; full backend suite
780 passed; full frontend suite 93 passed; production build passed. Isolated
browser smoke with mocked API responses verified busy/success/error feedback,
selector updates, legacy Workspace tab fallback, no Workspace requests and no
runtime errors or page overflow at 1024, 1440 and 1920px. This smoke did not run
a live provider backtest. Existing build chunk-size and Starlette/httpx deprecation
warnings remain.
