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

Position drawings retain entry, stop, target and a horizontal extent anchor. Replay copies these prices into its order ticket, while risk and planned R:R remain calculated outputs.

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

## Phase 6.1.3 interaction rules

- Crosshair/navigation is the normal chart mode and is also the selection mode for existing drawings.
- Existing drawings should be selectable directly without switching into a separate selection tool.
- Horizontal drawings display their exact price on the chart edge.
- The chart crosshair exposes both the candle OHLC under the vertical crosshair and the exact cursor price under the horizontal crosshair.
- Freehand strokes are single objects: copy/paste/delete and styling are supported, but individual sampled points are intentionally not resize handles.
- Long/short position tools place a pre-sized analysis object from one click, then allow Entry / Stop / Target / horizontal extent to be resized. R:R is always derived from those prices.
- Fib levels, visibility, colours and background fill are object settings, not hard-coded chart constants.

## Current interactions and efficiency

Drawings invalidate on chart primitive/time-scale/resize events; there is no idle
animation loop. Detach primitives before chart disposal. Screen projections are
transient; persisted timestamp/price points remain unchanged by timeframe changes.
Magnet lookup uses the nearest logical bar and its four OHLC values. Shift constrains
two-point drawing angles. Whole brush objects move; sampled points remain uneditable.
Object settings can Save tool defaults or Reset tool defaults without copying IDs,
anchors or lock state. Templates save timeframe/session/indicators/display options,
never symbols or drawings. Preferences are browser-local.
PriceChart uses incremental candle/volume updates for latest/append changes and
setData for initial load, corrected history, prepend, rewind or lattice replacement.
Replay increments candles only from already-revealed responses. Indicators still
rebuild their chart series; there is no new lower-pane framework or live tick feed.
Historical workflow handoffs request a bounded period around the trade timestamp.
