# Documentation and test cleanup audit

3 October 2026, Stage 11. Scope: current README/docs and test sources. No runtime,
installed dependency, credential or data file was opened/deleted for this cleanup.

## Deleted documents

| File | Why safe | Useful content preserved in |
|---|---|---|
| `docs/RC_FINAL_PASS.md` | Historical RC implementation narrative; superseded by current feature docs. Source/config/build reference search found only its companion verification link, no runtime/discovery/migration dependency. | Journal review/Analysis details in JOURNAL; drawing/Replay contracts in CHART_WORKSPACE; run/viewer details in BACKTEST_WORKFLOW; Screener details in ARCHITECTURE; synthetic-demo warnings in RUNNING_LEDGER |
| `docs/FINAL_RC_VERIFICATION.md` | Historical Linux/dependency-blocked results and RC packaging notes, superseded by successful current Windows tests/build. Only the deleted RC narrative referenced it. | Manual acceptance checks and isolated verification instructions in VERIFICATION; current exact counts/limits in RELIABILITY_ACCEPTANCE |

Both documents remain available in Git history. Their old synthetic-demo counts
are historical load samples, not schema or migration requirements. No obsolete
instruction to delete/reinstall working node_modules was retained.

## Corrected references and stale claims

- Removed README links to absent AGENTS.md and CODEX_WORKFLOW.md; neither is available
  in this tree. Did not invent replacement engineering rules or weaken constraints.
- Removed the instruction to copy the absent backend/.env.example. Current provider
  configuration docs remain linked; a safe example is a separate pending stage.
- Release history/roadmap no longer link to absent RELEASE_CHECKPOINT_12.md.
- Research experiments link to the existing measured benchmark, not absent
  RESEARCH_BENCHMARKS.md.
- Backtest docs now describe the global CPU budget, separate preparation, expandable
  research and dedicated Run Viewer, rather than the superseded two-thread/mode UI.
- Architecture uses the real 20-row default / 100-row expansion; drawing persistence
  is no longer incorrectly described as entirely future work.
- docs/README.md indexes the authoritative current workflow, strategy and operations
  documents. The original audit and implementation evidence remain clearly labelled.

## Tests and fixtures

99 direct backend/frontend test source files were checked for byte-identical
nonempty duplicates: none found. All 737 backend and 88 frontend tests passed at the
accepted code; 99 focused reliability acceptance tests passed again. No failing
unit test was blindly deleted. No demonstrably dead fixture was identified.

- Production regressions: addressed and tested in stages 1, 3-8; preserve coverage.
- Valid behaviour/stale contracts: earlier axis signature and browser wording tests
  were corrected in Stage 2, retaining numerical and causal assertions.
- Genuinely obsolete/duplicate tests: none established; **zero tests/fixtures deleted**.

Historical phase/checkpoint test filenames are not evidence of obsolete behaviour.
They remain valuable for no-lookahead, fills, futures provenance, research parity,
broker reconciliation, Journal preservation and Replay. Older opt-in browser scripts
are retained; this cleanup does not claim all were rerun or that source hashing
proves absence of semantic overlap.

Validation after cleanup: full backend/frontend/build and local Markdown link checks
are recorded in the implementation status. References to the two deleted filenames
in this audit are intentional deletion evidence, not broken navigation links.
