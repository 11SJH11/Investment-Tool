# Shared chart workspace — Phase 6.1

Phase 6.1 introduces the first shared drawing/workspace layer used by **Charts** and **Replay**.

## Drawing coordinate model

Drawings are stored in **market coordinates** rather than pixels:

- X anchor: Unix timestamp
- Y anchor: market price

The SVG interaction layer converts timestamp/price anchors to screen coordinates using Lightweight Charts. This keeps drawings attached to the same market locations when the chart is resized, panned, zoomed or rendered at another timeframe.

Replay receives only the currently revealed bars, so a Replay drawing cannot anchor to a hidden future candle.

## Tools in 6.1

- chart crosshair/navigation
- select/move drawing
- trend line
- horizontal line
- horizontal ray
- vertical line
- arrow
- rectangle/zone
- brush/freehand
- text note
- Fibonacci retracement
- long position
- short position
- weak/strong/off OHLC magnet
- undo/redo
- hide/show
- lock/unlock
- delete
- colour and line-width editing
- text editing for text drawings

Position drawings use three anchors: **entry -> stop -> target**. Replay copies these prices into its order ticket, while risk and planned R:R remain calculated outputs.

## Persistence

Phase 6.1 persists chart drawings in browser-local storage by workspace/symbol. Chart drawings are shared across that symbol's timeframes. Replay drawings are scoped to the replay symbol/start date/start time and include `created_at_replay_timestamp` metadata when created.

This is intentionally a frontend persistence foundation. Moving chart layouts/drawings into SQLite is a future option if cross-browser/device persistence becomes useful.

## Still later

- Pitchfork and Gann families
- Fib extensions/fans/time zones
- dedicated FVG/liquidity/BOS semantic tools
- drawing templates/groups/layer ordering
- synced drawings/crosshair across 2/4-chart layouts
- full lower-pane framework for RSI/MACD/ATR/Volume
- right-click chart commands
- drawing-based alerts
- anchored VWAP drawing
- advanced measurement/pattern tools
