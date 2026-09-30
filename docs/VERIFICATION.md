# Verification

Run `powershell -ExecutionPolicy Bypass -File ./Verify-Ledger.ps1` from the repository
root after installing `backend/requirements-dev.txt` and frontend dependencies.
The execution-policy switch applies to this verification process only.

It runs the full backend suite, frontend utility tests and production build,
failing on the first unsuccessful phase. Tests disable dotenv parsing and use
temporary databases. Python bytecode output is disabled. The production build
also disables dotenv reading and writes outside the repository. It does not
restart Ledger, alter installed dependencies, or access the live database.
Optional `-OutputDirectory` must be outside the repository. The artifact path
is printed for isolated browser checks. Run `git diff --check` before committing.

Browser scripts under `frontend/tests/browser` are opt-in and require an isolated
browser profile/server. Never aim fixtures at the live application database.

## Continuous-futures warm-cache contract

While source/reference evidence remains valid, identical covered requests return
identical OHLCV/source-contract provenance with zero additional provider calls.
The first derived Parquet read after cold construction or restart may read disk.
Subsequent in-memory hits avoid physical Parquet reads. Memory expiry/eviction
is not a reason to redownload durable history. Reference expiry or explicit
refresh can legitimately require provider validation.

Tests cover cold/warm equality, provider-call counts, a memory hit, cleared-memory
new-service reconstruction and isolation from caller mutation.
