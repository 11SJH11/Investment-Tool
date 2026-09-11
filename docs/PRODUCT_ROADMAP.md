# Ledger product roadmap after Phase 6.1

## Main navigation
- Dashboard: temporary product/TODO dashboard; later becomes polished app overview.
- Screener: local stock scanner plus watchlist/favourites.
- Charts: 1/2/4-chart analysis workspace, indicators and shared drawing tools.
- Replay: candle-by-candle practice with future data hidden, orders, indicators and the shared drawing tools.
- Journal: manual live/paper logs, automatic replay logs, analysis, calendar, daily review and playbook.
- Backtest: coded strategies, validation, saved runs, sensitivity and trade audit.
- Investment Portfolio: long-term investment ledger.
- Settings: appearance, chart/drawing defaults, navigation order and data/provider maintenance.

## Next trading work
1. Define First Pullback v1 objectively and implement as a strategy plugin.
2. Audit recognised setups before optimising parameters.
3. Development -> validation -> out-of-sample testing.
4. Practise the same strategy in Replay and compare with backtest results.
5. Define AMN objectively and repeat.

## Chart roadmap
Phase 6.1 adds the common market-coordinate drawing layer, 1/2/4 chart sizing, per-chart indicators, maximise/restore, object management, Fib retracement, long/short position tools and drawing persistence.

Still later:
- proper lower panes for Volume/RSI/MACD/ATR
- Pitchfork/Gann/advanced Fib families
- saved indicator templates and complete chart layouts
- synced crosshair/time range/drawings across multi-chart layouts
- drawing groups/templates and advanced layer management
- right-click chart actions and drawing-based alerts
- Futures data provider (NQ/MNQ/ES) with futures-specific sessions

## Watchlist
Phase 6.1 adds a browser-local favourite-symbol watchlist. It is available before Screener filters, on Charts and Replay, and in symbol search results. Initial convenience symbols are AAPL, MSFT, AMD, NVDA, SPY and QQQ. NQ1! remains unavailable until a futures-capable data provider is added.

## Journal roadmap
Phase 6 adds filtered analysis by symbol, setup, entry hour, weekday, timeframe, direction, market condition and source. Later additions: broker imports, execution/fill model, MAE/MFE as first-class columns, exit analysis, risk adherence, liquidity reports where data supports them, tags, report presets, and richer comparison charts.

### Futures / metals provider phase
- Massive Futures provider for CME/CBOT/NYMEX/COMEX contract bars/reference/schedules.
- Dated NQ/GC contract lookup and symbol search.
- Ledger continuous aliases (`NQ1!`, `GC1!`, later micros) with explicit roll metadata.
- TradingView-style volume-derived roll schedule and optional back-adjustment.
- Futures sessions, tick size, point value and contract multiplier in backtest/replay execution math.
- Optional OANDA provider for `XAU_USD`/FX when the strategy specifically uses that feed rather than COMEX futures.
