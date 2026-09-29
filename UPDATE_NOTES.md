# Ledger update notes — 2026-09-28

This source snapshot contains the in-progress Ledger research/performance/cache update.

## Implemented
- Parent research experiments with persisted spectrum/interaction metadata.
- Dedicated research history + spectrum/heatmap viewer with drill-down to exact child runs.
- Interaction relationship analysis and direct band/range axes (lower-inclusive, upper-exclusive).
- Global backtest CPU worker preference UI and parent experiment worker resolution.
- Persistent favourite-symbol cache warming through the existing market-data cache.
- NQ1! warm path using dated futures contracts, roll/reference provenance, and continuous reconstruction.
- ORB research upper bounds: max breakout ATR and max opening-range RVOL.
- Failed-ORB reversal v1 with configurable failure window, filters, stop at failed-breakout extreme, and multiple target modes.
- Added tests for research infrastructure, ORB participation/bands and failed-ORB behaviour.

## Verification in this environment
- Python compileall for backend/app and backend/tests completed successfully.
- Frontend production build could not be run in the Linux sandbox because the uploaded node_modules contains Windows/native Rolldown bindings. Reinstalling frontend dependencies on the target Windows machine should resolve that environment mismatch.
- Full end-to-end/manual verification was intentionally not completed before packaging; please test this snapshot locally.

## Packaging
- backend/.env is intentionally excluded and was not inspected. Keep your existing .env.
- .venv, node_modules, .git, runtime logs and generated frontend dist are excluded.
- Keep your existing user data/cache/database when replacing source files.
