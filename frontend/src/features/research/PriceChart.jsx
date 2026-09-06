import { useEffect, useRef, useState } from "react";
import { CandlestickSeries, ColorType, HistogramSeries, LineSeries, createChart } from "lightweight-charts";
import { resolvedZone } from "../../utils/timezones";
import DrawingOverlay from "../../components/chart/DrawingOverlay";

function formatTimestamp(seconds, zone, withDate = false) {
  const date = new Date(Number(seconds) * 1000);
  const options = withDate
    ? { timeZone: resolvedZone(zone), day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }
    : { timeZone: resolvedZone(zone), hour: "2-digit", minute: "2-digit", hourCycle: "h23" };
  return new Intl.DateTimeFormat("en-GB", options).format(date);
}

function cleanBars(bars) {
  const seen = new Set();
  return (bars || []).map((bar) => ({
    time: Math.floor(new Date(bar.timestamp).getTime() / 1000),
    open: Number(bar.open), high: Number(bar.high), low: Number(bar.low), close: Number(bar.close), volume: Number(bar.volume || 0),
  })).filter((bar) => Number.isFinite(bar.time) && !seen.has(bar.time) && seen.add(bar.time)).sort((a, b) => a.time - b.time);
}

export default function PriceChart({
  bars,
  overlays = [],
  timeZone = "America/New_York",
  expanded = false,
  height = 520,
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
  showVolume = true,
  fill = false,
  initialVisibleBars = 180,
  onNeedMoreHistory,
}) {
  const ref = useRef(null);
  const chartRef = useRef(null);
  const candleRef = useRef(null);
  const volumeRef = useRef(null);
  const overlayRefs = useRef([]);
  const initialisedRef = useRef(false);
  const loadingHistoryRef = useRef(false);
  const onNeedMoreHistoryRef = useRef(onNeedMoreHistory);
  const [chartState, setChartState] = useState(null);

  useEffect(() => { onNeedMoreHistoryRef.current = onNeedMoreHistory; }, [onNeedMoreHistory]);

  useEffect(() => {
    if (!ref.current) return undefined;
    const style = getComputedStyle(document.documentElement);
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: style.getPropertyValue("--ledger-chart-background").trim() || "#111111" }, textColor: style.getPropertyValue("--ledger-chart-text").trim() || "#a8a29e" },
      grid: { vertLines: { color: style.getPropertyValue("--ledger-chart-grid").trim() || "#262626" }, horzLines: { color: style.getPropertyValue("--ledger-chart-grid").trim() || "#262626" } },
      rightPriceScale: { borderColor: style.getPropertyValue("--ledger-chart-border").trim() || "#333333" },
      timeScale: {
        borderColor: style.getPropertyValue("--ledger-chart-border").trim() || "#333333", timeVisible: true, secondsVisible: false,
        tickMarkFormatter: (time) => formatTimestamp(time, timeZone, false), rightOffset: 5,
      },
      localization: { timeFormatter: (time) => formatTimestamp(time, timeZone, true) },
      crosshair: { vertLine: { color: "#6b7280" }, horzLine: { color: "#6b7280" } },
      handleScroll: true,
      handleScale: true,
    });
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: style.getPropertyValue("--ledger-candle-up").trim() || "#22c55e",
      downColor: style.getPropertyValue("--ledger-candle-down").trim() || "#ef4444",
      borderVisible: false,
      wickUpColor: style.getPropertyValue("--ledger-candle-up").trim() || "#22c55e",
      wickDownColor: style.getPropertyValue("--ledger-candle-down").trim() || "#ef4444",
    });
    const volume = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "", priceLineVisible: false });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    chartRef.current = chart; candleRef.current = candles; volumeRef.current = volume;
    setChartState({ chart, candles });

    const rangeHandler = (range) => {
      if (!range || range.from == null || loadingHistoryRef.current) return;
      if (Number(range.from) < 35 && onNeedMoreHistoryRef.current) {
        loadingHistoryRef.current = true;
        Promise.resolve(onNeedMoreHistoryRef.current()).finally(() => {
          globalThis.setTimeout(() => { loadingHistoryRef.current = false; }, 500);
        });
      }
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(rangeHandler);
    return () => {
      try { chart.timeScale().unsubscribeVisibleLogicalRangeChange(rangeHandler); } catch { /* ignored */ }
      chart.remove(); chartRef.current = null; candleRef.current = null; volumeRef.current = null; overlayRefs.current = []; setChartState(null); initialisedRef.current = false;
    };
  }, [timeZone]);

  useEffect(() => {
    const chart = chartRef.current, candles = candleRef.current, volume = volumeRef.current;
    if (!chart || !candles || !volume || !bars?.length) return;
    const clean = cleanBars(bars);
    if (!clean.length) return;
    const visibleTime = initialisedRef.current ? chart.timeScale().getVisibleRange() : null;
    candles.setData(clean.map(({ volume: _, ...bar }) => bar));
    volume.applyOptions({ visible: showVolume });
    volume.setData(clean.map((bar) => ({ time: bar.time, value: bar.volume, color: bar.close >= bar.open ? "rgba(52,211,153,.24)" : "rgba(248,113,113,.24)" })));

    if (!initialisedRef.current) {
      const from = Math.max(0, clean.length - Math.max(60, Number(initialVisibleBars || 180)));
      try { chart.timeScale().setVisibleLogicalRange({ from, to: clean.length + 5 }); } catch { chart.timeScale().fitContent(); }
      initialisedRef.current = true;
    } else if (visibleTime?.from != null && visibleTime?.to != null) {
      requestAnimationFrame(() => {
        try { chart.timeScale().setVisibleRange(visibleTime); } catch { /* old range may be outside the newly selected symbol */ }
      });
    }
  }, [bars, showVolume, initialVisibleBars]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    overlayRefs.current.forEach((series) => { try { chart.removeSeries(series); } catch { /* ignored */ } });
    overlayRefs.current = [];
    const styles = [
      { color: "#60a5fa", lineWidth: 2 }, { color: "#f59e0b", lineWidth: 2 }, { color: "#a78bfa", lineWidth: 2 },
      { color: "#22c55e", lineWidth: 2 }, { color: "#06b6d4", lineWidth: 2 }, { color: "#f43f5e", lineWidth: 2 },
    ];
    overlays.filter((overlay) => overlay.visible !== false).forEach((overlay, index) => {
      const series = chart.addSeries(LineSeries, {
        ...styles[index % styles.length], color: overlay.color || styles[index % styles.length].color,
        lineWidth: Number(overlay.lineWidth || 2), title: overlay.label || overlay.key,
        priceLineVisible: false, lastValueVisible: true,
      });
      const values = (overlay.values || []).map((point) => ({ time: Math.floor(new Date(point.timestamp).getTime() / 1000), value: Number(point.value) }))
        .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value));
      series.setData(values); overlayRefs.current.push(series);
    });
  }, [overlays]);

  return <div className={`relative w-full ${fill || expanded ? "h-full" : ""}`} style={!expanded && !fill ? { height } : undefined}>
    <div ref={ref} className="h-full w-full" />
    {chartState && <DrawingOverlay
      chart={chartState.chart}
      series={chartState.candles}
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
    />}
  </div>;
}
