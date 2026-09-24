import {seriesChange} from "../../components/chart/seriesUpdates.js";
import { useEffect, useMemo, useRef, useState } from "react";
import { CandlestickSeries, ColorType, CrosshairMode, HistogramSeries, LineSeries, LineStyle, createChart, createSeriesMarkers } from "lightweight-charts";
import { resolvedZone } from "../../utils/timezones";
import DrawingOverlay from "../../components/chart/DrawingOverlay";

function seconds(value) { return Math.floor(new Date(value).getTime() / 1000); }
function labelTime(time, zone, withDate = false) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: resolvedZone(zone), ...(withDate ? { day: "2-digit", month: "short" } : {}),
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).format(new Date(Number(time) * 1000));
}
function cleanBars(bars) {
  const seen = new Set();
  return (bars || []).map((bar) => ({ time: seconds(bar.timestamp), open: Number(bar.open), high: Number(bar.high), low: Number(bar.low), close: Number(bar.close), volume: Number(bar.volume || 0) }))
    .filter((bar) => Number.isFinite(bar.time) && !seen.has(bar.time) && seen.add(bar.time)).sort((a, b) => a.time - b.time);
}
function medianStep(clean) {
  const steps = [];
  for (let i = 1; i < Math.min(clean.length, 100); i += 1) {
    const d = clean[i].time - clean[i - 1].time;
    if (d > 0 && d < 86400) steps.push(d);
  }
  if (!steps.length) return 60;
  steps.sort((a, b) => a - b); return steps[Math.floor(steps.length / 2)] || 60;
}
function timeAtLogical(clean, logical) {
  if (!clean.length || logical == null || !Number.isFinite(Number(logical))) return null;
  const value = Number(logical), step = medianStep(clean);
  if (value <= 0) return clean[0].time + value * step;
  if (value >= clean.length - 1) return clean[clean.length - 1].time + (value - (clean.length - 1)) * step;
  const left = Math.floor(value), right = Math.ceil(value), f = value - left;
  return clean[left].time + (clean[right].time - clean[left].time) * f;
}
function logicalAtTime(clean, time) {
  if (!clean.length || time == null || !Number.isFinite(Number(time))) return null;
  const target = Number(time), step = medianStep(clean);
  if (target <= clean[0].time) return (target - clean[0].time) / step;
  if (target >= clean[clean.length - 1].time) return (clean.length - 1) + (target - clean[clean.length - 1].time) / step;
  let lo = 0, hi = clean.length - 1;
  while (lo + 1 < hi) { const mid = (lo + hi) >> 1; if (clean[mid].time <= target) lo = mid; else hi = mid; }
  const span = Math.max(1, clean[hi].time - clean[lo].time);
  return lo + (target - clean[lo].time) / span;
}

export default function ReplayChart({
  bars,
  timeframe = "",
  overlays = [],
  timeZone = "America/New_York",
  position = null,
  closedTrade = null,
  pendingOrder = null,
  expanded = false,
  followReplay = false,
  jumpToken = 0,
  showVolume = true,
  volumeStyle = null,
  drawingTool = "cursor",
  magnet = "weak",
  drawings = [],
  selectedDrawingId = null,
  onSelectDrawing,
  onDrawingsChange,
  onDrawingToolChange,
  onPositionDrawing,
  onUndoDrawing,
  onRedoDrawing,
  onDeleteDrawing,
  drawingMeta = {},
}) {
  const ref = useRef(null);
  const chartRef = useRef(null);
  const candlesRef = useRef(null);
  const volumeRef = useRef(null);
  const overlayRefs = useRef([]);
  const priceLinesRef = useRef([]);
  const initialisedRef = useRef(false);
  const previousCleanRef = useRef([]);
  const [chartReady, setChartReady] = useState(0);
  const [crosshairInfo, setCrosshairInfo] = useState(null);
  const clean = useMemo(() => cleanBars(bars), [bars]);

  useEffect(() => {
    if (!ref.current) return undefined;
    const style = getComputedStyle(document.documentElement);
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: style.getPropertyValue("--ledger-chart-background").trim() || "#111111" }, textColor: style.getPropertyValue("--ledger-chart-text").trim() || "#a8a29e" },
      grid: { vertLines: { color: style.getPropertyValue("--ledger-chart-grid").trim() || "#262626" }, horzLines: { color: style.getPropertyValue("--ledger-chart-grid").trim() || "#262626" } },
      rightPriceScale: { borderColor: style.getPropertyValue("--ledger-chart-border").trim() || "#333333" },
      timeScale: { borderColor: style.getPropertyValue("--ledger-chart-border").trim() || "#333333", timeVisible: true, secondsVisible: false, tickMarkFormatter: (time) => labelTime(time, timeZone), rightOffset: 8 },
      localization: { timeFormatter: (time) => labelTime(time, timeZone, true) },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "#758696", width: 1, style: LineStyle.Dashed, labelVisible: true, labelBackgroundColor: "#4c525e" },
        horzLine: { color: "#758696", width: 1, style: LineStyle.Dashed, labelVisible: true, labelBackgroundColor: "#4c525e" },
      },
      handleScroll: true, handleScale: true,
    });
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: style.getPropertyValue("--ledger-candle-up").trim() || "#22c55e", downColor: style.getPropertyValue("--ledger-candle-down").trim() || "#ef4444", borderVisible: false,
      wickUpColor: style.getPropertyValue("--ledger-candle-up").trim() || "#22c55e", wickDownColor: style.getPropertyValue("--ledger-candle-down").trim() || "#ef4444",
    });
    const volume = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "", priceLineVisible: false });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    chartRef.current = chart; candlesRef.current = candles; volumeRef.current = volume;
    const crosshairHandler = (param) => {
      if (!param?.point) { setCrosshairInfo(null); return; }
      const candle = param.seriesData?.get?.(candles);
      setCrosshairInfo({ candle: candle && Number.isFinite(Number(candle.close)) ? candle : null });
    };
    chart.subscribeCrosshairMove(crosshairHandler);
    initialisedRef.current = false; previousCleanRef.current = [];
    setChartReady((v) => v + 1);
    return () => {
      try { chart.unsubscribeCrosshairMove(crosshairHandler); } catch { /* ignored */ }
      chart.remove(); chartRef.current = null; candlesRef.current = null; volumeRef.current = null;
      overlayRefs.current = []; priceLinesRef.current = []; previousCleanRef.current = [];
    };
  }, [timeZone]);

  useEffect(() => {
    const chart = chartRef.current, candles = candlesRef.current, volume = volumeRef.current;
    if (!chart || !candles || !volume || !clean.length) return;
    const previous = previousCleanRef.current;
    const logicalRange = initialisedRef.current ? chart.timeScale().getVisibleLogicalRange() : null;
    const marketWindow = logicalRange && previous.length ? {
      from: timeAtLogical(previous, logicalRange.from), to: timeAtLogical(previous, logicalRange.to),
    } : null;
    const appendOnly = previous.length > 0 && clean.length >= previous.length && clean[0]?.time === previous[0]?.time && clean[previous.length - 1]?.time === previous[previous.length - 1]?.time;

    const change=seriesChange(previous,clean);
    const candleData=clean.map(({volume:_,...bar})=>bar);
    if(change.mode==="replace")candles.setData(candleData);else candleData.slice(change.from).forEach(b=>candles.update(b));
    volume.applyOptions({ visible: showVolume });
    const upVolume = volumeStyle?.upColor || "#34d399", downVolume = volumeStyle?.downColor || "#f87171", volumeOpacity = Number(volumeStyle?.opacity ?? .28);
    const volumeHex = (color, opacity) => { if (!/^#[0-9a-fA-F]{6}$/.test(color)) return color; const alpha=Math.round(Math.max(0,Math.min(1,opacity))*255).toString(16).padStart(2,"0"); return `${color}${alpha}`; };
    volume.setData(clean.map((bar) => ({ time: bar.time, value: bar.volume, color: volumeHex(bar.close >= bar.open ? upVolume : downVolume, volumeOpacity) })));

    if (!initialisedRef.current) {
      chart.timeScale().fitContent();
      initialisedRef.current = true;
    } else if (followReplay) {
      chart.timeScale().scrollToRealTime();
    } else if (appendOnly && logicalRange?.from != null && logicalRange?.to != null) {
      // Follow OFF means the viewport is the user's. Keep the exact logical window,
      // including any empty space to the right where newly revealed candles can grow.
      requestAnimationFrame(() => { try { chart.timeScale().setVisibleLogicalRange(logicalRange); } catch { /* ignored */ } });
    } else if (marketWindow?.from != null && marketWindow?.to != null) {
      // A timeframe switch replaces the bar lattice. Rebuild the same timestamp window
      // on the new lattice instead of jumping to the newest candle.
      const from = logicalAtTime(clean, marketWindow.from), to = logicalAtTime(clean, marketWindow.to);
      if (from != null && to != null) requestAnimationFrame(() => { try { chart.timeScale().setVisibleLogicalRange({ from, to }); } catch { /* ignored */ } });
    }
    previousCleanRef.current = clean;
  }, [clean, followReplay, showVolume, volumeStyle,chartReady]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    overlayRefs.current.forEach((series) => { try { chart.removeSeries(series); } catch { /* already gone */ } });
    overlayRefs.current = [];
    overlays.filter((overlay) => overlay.overlay && overlay.visible !== false).forEach((overlay) => {
      const series = chart.addSeries(LineSeries, {
        color: overlay.color || "#60a5fa", lineWidth: Number(overlay.lineWidth || 2),
        title: overlay.label || overlay.key, priceLineVisible: false, lastValueVisible: true,
      });
      const values = (overlay.values || []).map((point) => ({ time: seconds(point.timestamp), value: Number(point.value) }))
        .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value));
      series.setData(values); overlayRefs.current.push(series);
    });
  }, [overlays,chartReady]);

  useEffect(() => {
    const candles = candlesRef.current;
    if (!candles) return;
    priceLinesRef.current.forEach((line) => { try { candles.removePriceLine(line); } catch { /* ignored */ } });
    priceLinesRef.current = [];
    const active = position || closedTrade;
    const order = pendingOrder && !active ? pendingOrder : null;
    const addLine = (price, title, options = {}) => {
      if (price == null || !Number.isFinite(Number(price))) return;
      priceLinesRef.current.push(candles.createPriceLine({ price: Number(price), title, lineWidth: 1, axisLabelVisible: true, ...options }));
    };
    if (active) {
      addLine(active.entry_price, "Entry", { lineWidth: 2 }); addLine(active.stop_loss, "Stop", { lineStyle: 2 }); addLine(active.take_profit, "Target", { lineStyle: 2 });
    } else if (order) {
      if (order.order_type !== "market") addLine(order.entry_price, `${order.order_type} entry`, { lineWidth: 2 });
      addLine(order.stop_loss, "Stop", { lineStyle: 2 }); addLine(order.take_profit, "Target", { lineStyle: 2 });
    }
    const markers = [];
    if (active?.entry_time) markers.push({ time: seconds(active.entry_time), position: active.direction === "long" ? "belowBar" : "aboveBar", shape: active.direction === "long" ? "arrowUp" : "arrowDown", color: "#60a5fa", text: `${active.direction.toUpperCase()} ENTRY` });
    if (closedTrade?.exit_time) markers.push({ time: seconds(closedTrade.exit_time), position: closedTrade.direction === "long" ? "aboveBar" : "belowBar", shape: closedTrade.direction === "long" ? "arrowDown" : "arrowUp", color: closedTrade.net_pnl >= 0 ? "#22c55e" : "#ef4444", text: `EXIT ${closedTrade.exit_reason}` });
    createSeriesMarkers(candles, markers.sort((a, b) => a.time - b.time));
  }, [position, closedTrade, pendingOrder,chartReady]);

  useEffect(() => { if (jumpToken && chartRef.current) chartRef.current.timeScale().scrollToRealTime(); }, [jumpToken]);

  return <div className={expanded ? "relative h-full min-h-0 w-full" : "relative h-full min-h-[420px] w-full"}>
    <div ref={ref} className="h-full w-full" />
    {crosshairInfo && <div className="chart-crosshair-readout">
      {crosshairInfo.candle && <span><b>O</b> {Number(crosshairInfo.candle.open).toFixed(2)} <b>H</b> {Number(crosshairInfo.candle.high).toFixed(2)} <b>L</b> {Number(crosshairInfo.candle.low).toFixed(2)} <b>C</b> {Number(crosshairInfo.candle.close).toFixed(2)}</span>}
    </div>}
    {chartReady > 0 && chartRef.current && candlesRef.current && <DrawingOverlay key={`drawings-${timeframe || "default"}`}
      chart={chartRef.current}
      series={candlesRef.current}
      container={ref.current}
      tool={drawingTool}
      magnet={magnet}
      bars={bars}
      drawings={drawings}
      selectedId={selectedDrawingId}
      onSelect={onSelectDrawing}
      onChange={onDrawingsChange}
      onToolChange={onDrawingToolChange}
      onPositionDrawing={onPositionDrawing}
      onUndo={onUndoDrawing}
      onRedo={onRedoDrawing}
      onDeleteSelected={onDeleteDrawing}
      drawingMeta={drawingMeta}
      clampToBars
    />}
  </div>;
}
