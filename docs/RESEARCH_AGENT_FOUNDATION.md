# Research Agent current status / handoff

The authoritative full update is [Research Agent major update - October 2026](RESEARCH_AGENT_MAJOR_UPDATE_2026-10.md).
It consolidates the work since committed boundary `afb73e9` (2026-10-05), including
Market Concepts, research workflows, storage, UI, provider integration and Docker.

Final verification (2026-10-10): **1,062 backend tests passed**, including
**18 real-Docker security/lifecycle tests** and **7 Docker research-loop tests**;
**128 frontend tests passed**; production build passed. Browser acceptance passed
at 1024/1440/1920 px. Final Docker inspection found zero Ledger research containers;
unrelated stopped containers remain untouched. No application/test edits followed
verification. Work remains uncommitted; see the full update for the exact inventory
and the pre-existing user-strategy whitespace advisory.

Current state (2026-10-10):

- Deterministic development research, bounded optional committee/loop, candidate
  checks, explicit validation and research decisions are implemented.
- Source archives, reproducibility manifests and evidence retention are implemented.
- Generated source stays quarantined; explicitly approved checks run only in offline
  Docker, using completed snapshots and the trusted host engine for accounting.
- Independent host guardian, cancellation, owned-container cleanup and restart
  reconciliation are implemented. Docker failure has no main-process fallback.
- Candidate UI exposes consent, progress, cancellation, parity and provenance.

See the major update for final verification counts, image identity, exact files,
security tests, limitations and step-by-step acceptance instructions.

Operational prerequisites: Linux/amd64 Docker with cgroups v2 and seccomp, one
Ledger backend per database, and an operator-built current sandbox image. Run
`backend/.venv/Scripts/python.exe -B backend/tools/build_research_sandbox.py`
from the repository root. No credentials or repository mounts enter the image.

Limits: one symbol / 10,000 aggregate bars / bounded deadline, explicit draft
approval, finite prefix testing, no generated-child automatic activation or
holdout grant. Live LLM/provider acceptance and complete data/image archival remain
external/operator responsibilities. Existing trusted Python strategy refresh is
a separate workflow and must not be used to execute unreviewed generated code.
