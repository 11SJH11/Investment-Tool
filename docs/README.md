# Ledger documentation

Use these current documents for each workflow. Historical names inside strategy
specifications describe frozen contracts; they are not instructions to redo a phase.

## Operating and verifying Ledger

- [Running Ledger](RUNNING_LEDGER.md): local startup, backups and deployment limits.
- [Verification](VERIFICATION.md): isolated full-suite/build command and manual checks.
- [Architecture](ARCHITECTURE.md): ownership, persistence and application boundaries.
- [Data sources](DATA_SOURCES.md): provider configuration and data limitations.
- [Market-cache warming](MARKET_CACHE_WARMING.md): priority, pause/resume and recovery.
- [Third-party notices](THIRD_PARTY.md): licensing and acknowledgements.

## User and developer workflows

- [Charts and Replay](CHART_WORKSPACE.md): drawings, causality and local checkpoints.
- [Journal](JOURNAL.md): reviews, Playbook, Daily Review, analytics and preservation.
- [Backtest workflow](BACKTEST_WORKFLOW.md): configuration, queue and saved runs.
- [Research experiments](RESEARCH_EXPERIMENTS.md): exact spectra/grids and CPU budget.
- [Research diagnostics](RESEARCH_DIAGNOSTICS.md): Run Viewer metrics and exports.
- [Strategy refresh](STRATEGY_REFRESH.md): direct Python files, safe registry updates and provenance.
- [Legacy Workspace backend](STRATEGY_WORKSPACE.md): retained drafts/history and API reference.
- [Strategy Lab internals](STRATEGY_LAB.md): engine/interface and historical contracts;
  current user navigation lives in Backtest workflow.
- [Strategy plugin template](STRATEGY_PLUGIN_TEMPLATE.md) and
  [indicator plugin template](INDICATOR_PLUGIN_TEMPLATE.md).
- [Broker connections](BROKER_CONNECTIONS.md): supported read-only connections.
- [Broker import acceptance](BROKER_IMPORT_ACCEPTANCE.md): fixtures, verification, cleanup and limitations.
- [Broker extension contract](BROKER_EXTENSION_CONTRACT.md): future adapter boundaries.

## Frozen strategy and instrument contracts

- [Futures economics](FUTURES_FOUNDATION.md) and
  [continuous futures](CONTINUOUS_FUTURES_RESEARCH.md): raw execution, rolls and evidence.
- [Momentum/VCP](MOMENTUM_VCP_BASELINE_V1.md).
- [ORB/VWAP baselines](ORB_VWAP_BASELINES.md) and
  [ORB research diagnostics](ORB_RESEARCH_DIAGNOSTICS.md).
- [Gold experiments](GOLD_EXPERIMENTS.md).

## Current acceptance and engineering records

- [Reliability acceptance](RELIABILITY_ACCEPTANCE.md): scope, root causes, tests and
  [recorded 5x5 benchmark](GLOBAL_BUDGET_BENCHMARK.json).
- [Implementation status](RELIABILITY_IMPLEMENTATION_STATUS.md): completed/pending stages.
- [Cleanup audit](CLEANUP_AUDIT.md): exact deletions, evidence and retained tests.
- [Release history](RELEASE_CHECKPOINTS.md) and [roadmap](PRODUCT_ROADMAP.md).
- [Original application audit](COMPREHENSIVE_APPLICATION_AUDIT_2026-09-29.md): historical
  findings, retained as evidence; use current acceptance for resolved issues.

Ledger remains a trusted local application. Do not expose it publicly, run fixtures
against live data, or treat current-universe stock results as survivorship-free.
TradeLocker/MT5 implementation is pending until the status document says otherwise.
