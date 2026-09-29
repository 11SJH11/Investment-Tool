# Reliability and broker import implementation status

## Safety checkpoint

- Source checkpoint: `4dc3da4`, branch `checkpoint/pre-reliability-2026-09-29`.
- Runtime logs/bytecode were already dirty and were not added to the checkpoint.
- Do not read/edit `.env`, touch live `data/`, restart the running research service,
  or change strategy rules, engine semantics, fills, sizing, or market-data values.
- Tests use temporary storage. Test settings disable dotenv parsing entirely.

## Stages

| Stage | Scope | Status |
|---|---|---|
| 1 | Separate research notes/items and experiments | Complete: 18 focused tests pass |
| 2 | Restore green verification gate | In progress |
| 3 | Crash-safe raw market cache | Pending |
| 4 | Bounded, resumable, interactive-priority warming | Pending |
| 5 | Global simulation budget and 5×5 parity benchmark | Pending |
| 6 | Compact research polling | Pending |
| 7 | Replay leave/checkpoint guard | Pending |
| 8 | Safe actionable error categories | Pending |
| 9–10 | Protected scope and final acceptance | Pending final verification |
| 11 | Documentation/test classification and cleanup | Pending |
| 12 | TradeLocker read-only import | Pending official API review |
| 13 | MetaTrader 5 read-only import | Pending official integration review |
| 14 | Canonical broker execution model | Pending |
| 15 | Broker frontend | Pending |
| 16 | Safe root `.env.example` | Pending |
| 17 | Untrack generated files, retain local copies | Pending |
| 18 | Broker fixture acceptance | Pending |

## Stage 1

Restored the original notes/items repository behaviour from source history as
`ResearchItemRepository`. Experiment persistence is now explicitly named
`ResearchExperimentRepository`. Existing tables and IDs are unchanged.
The old experiment import remains a compatibility alias for existing callers and
workers; it is not a combined repository. Tests exercise real container wiring,
API list/upsert/delete, source identity, distinct manual notes, restart preservation,
and coexistence with experiment documents.

Validation: `test_research_items_api.py`, `test_phase63_journal_research.py`,
`test_parent_research.py`: **18 passed**.

## Failure classification

- Missing research-item methods: **production regression**; restore production
  implementation and preserve the existing upsert test.
- 18 research-axis failures: **valid behaviour, stale test contract**; update the
  signature without removing numeric validation assertions.
- Continuous warm-cache physical-read assertion: **valid behaviour, stale contract**.
  Durable reuse promises identical data/provenance and zero provider requests while
  reference evidence remains valid. First disk reads after cold preparation/restart
  are allowed; subsequent in-memory hits are separately asserted.
- Browser research wording/view placement: **valid behaviour, stale test contract**.
  Follow current dedicated Research Viewer navigation.
- Removed heatmap corner-selection UI assertions: **obsolete UI workflow**; exact
  experiment generation, heatmaps, cell opening, and low-sample checks remain required.

No tests or documents have been deleted at this checkpoint.
