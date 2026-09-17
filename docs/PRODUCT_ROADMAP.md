# Ledger current product roadmap

## Implemented through checkpoint 6

- Charts and Replay share provider routing: US equities via Alpaca, XAUUSD via
  OANDA, futures via Massive. Continuous aliases have chart support with provenance;
  dated futures have multiplier/tick-aware Backtest and Replay execution.
- Replay reveals canonical one-minute bars before aggregation, preserves timeframes
  and integrity state, and idempotently journals closed trades.
- One Journal supports manual/Replay/broker sources, Playbook custom fields,
  Daily Review, attachments, filters, Analysis/Calendar and currency-separated totals.
- OANDA Journal history and Trading 212 Portfolio imports are read-only, with
  multiple profiles and account/environment identity. Tradovate is unsupported.
- Backtest has saved immutable snapshots, validation roles, sensitivity, Trade Audit,
  trusted local Strategy Workspace, frozen Gold/Momentum, ORB/VWAP, and Gold filter
  variants/comparison. DXY-dependent variants cannot validate performance yet.

## Required remaining release work

7. Release-wide checks and current-documentation cleanup.
8. TradingView-methodology research; versioned continuous roll schedules; NQ1!
   Backtest/Replay backed by raw dated-contract fills; cross-roll protection;
   durable Massive reference caching/rate-limit handling; targeted Trading 212
   investor metrics and universal broker-adapter extension audit.

Do not claim NQ1! execution or verified TradingView parity before that work passes.
No live orders, broker automation, fabricated roll data, silent currency mixing,
frozen-strategy tuning, user-data replacement or broad visual redesign.

## Later research and UX

Use development, validation and out-of-sample periods; change one hypothesis at a
time. First Pullback/AMN require agreed numerical definitions. Point-in-time DXY,
fundamentals/universes and explicit portfolio selection/capital rules are separate
work. Walk-forward and sensitivity tests must not automatically select a winner.

Advanced drawing tools, indicator panes/layouts, synchronized chart interactions
and reporting presets remain optional later work, not release blockers.

Checkpoint-specific documents are historical records. RELEASE_CHECKPOINTS.md is
the continuation index; detailed contracts are linked from ARCHITECTURE.md.
