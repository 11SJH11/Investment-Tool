import {loadPreferences} from "../../app/preferences.js";
import {seriesChange} from "../../components/chart/seriesUpdates.js";
import { useEffect, useRef, useState } from "react";
import { CandlestickSeries, ColorType, CrosshairMode, HistogramSeries, LineSeries, LineStyle, createChart } from "lightweight-charts";
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
  timeframe = "",
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
  volumeStyle = null,
  fill = false,
  initialVisibleBars = 180,
  onNeedMoreHistory,
  onCursorTime,
  focusTimestamp,
  settings,
}) {
  const preferences=settings||loadPreferences();
  const ref = useRef(null);
  const chartRef = useRef(null);
  const candleRef = useRef(null);
  const volumeRef = useRef(null);
  const overlayRefs = useRef([]);
  const initialisedRef = useRef(false);
  const previousBars=useRef([]);
  const previousContext=useRef(null);
  const previousVolumeStyle=useRef(null);
  const loadingHistoryRef = useRef(false);
  const cursorCallback=useRef(onCursorTime);cursorCallback.current=onCursorTime;
  const onNeedMoreHistoryRef = useRef(onNeedMoreHistory);
  const [chartState, setChartState] = useState(null);
  const [crosshairInfo, setCrosshairInfo] = useState(null);

  useEffect(() => { onNeedMoreHistoryRef.current = onNeedMoreHistory; }, [onNeedMoreHistory]);
  useEffect(()=>{
    if(!chartState)return;
    chartState.chart.applyOptions({grid:{vertLines:{visible:preferences.chartGridVisible!==false},horzLines:{visible:preferences.chartGridVisible!==false}},crosshair:{mode:preferences.chartCrosshair===false?CrosshairMode.Hidden:CrosshairMode.Normal},rightPriceScale:{autoScale:preferences.chartAutoScale!==false}});
    volumeRef.current?.applyOptions({visible:showVolume&&preferences.chartVolumeVisible!==false});
  },[chartState,preferences.chartGridVisible,preferences.chartCrosshair,preferences.chartAutoScale,preferences.chartVolumeVisible,showVolume]);


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
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "#758696", width: 1, style: LineStyle.Dashed, labelVisible: true, labelBackgroundColor: "#4c525e" },
        horzLine: { color: "#758696", width: 1, style: LineStyle.Dashed, labelVisible: true, labelBackgroundColor: "#4c525e" },
      },
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
    const crosshairHandler = (param) => {
      if (!param?.point || !ref.current) { setCrosshairInfo(null); return; }
      if(typeof param.time==="number")cursorCallback.current?.(new Date(param.time*1000).toISOString());
      const candle = param.seriesData?.get?.(candles);
      setCrosshairInfo({ candle: candle && Number.isFinite(Number(candle.close)) ? candle : null });
    };
    chart.subscribeCrosshairMove(crosshairHandler);

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
      try { chart.unsubscribeCrosshairMove(crosshairHandler); } catch { /* ignored */ }
      chart.remove(); chartRef.current = null; candleRef.current = null; volumeRef.current = null; overlayRefs.current = []; setChartState(null); initialisedRef.current = false; previousBars.current=[];
    };
  }, [timeZone]);

  useEffect(() => {
    const chart = chartRef.current, candles = candleRef.current, volume = volumeRef.current;
    if (!chart || !candles || !volume) return;
    const clean = cleanBars(bars);
    if (!clean.length) {candles.setData([]);volume.setData([]);previousBars.current=[];return;}
    const visibleTime = initialisedRef.current ? chart.timeScale().getVisibleRange() : null;
    const change=previousContext.current===timeframe?seriesChange(previousBars.current,clean):{mode:"replace",from:0};
    const candleData=clean.map(({ volume: _, ...bar }) => bar);
    if(change.mode==="replace")candles.setData(candleData);else candleData.slice(change.from).forEach(bar=>candles.update(bar));
    previousBars.current=clean;previousContext.current=timeframe;
    volume.applyOptions({ visible: showVolume && preferences.chartVolumeVisible!==false });
    const upVolume = volumeStyle?.upColor || "#34d399", downVolume = volumeStyle?.downColor || "#f87171", volumeOpacity = Number(volumeStyle?.opacity ?? .28);
    const volumeHex = (color, opacity) => {
      if (!/^#[0-9a-fA-F]{6}$/.test(color)) return color;
      const alpha = Math.round(Math.max(0, Math.min(1, opacity)) * 255).toString(16).padStart(2,"0"); return `${color}${alpha}`;
    };
    const volumeData=clean.map((bar) => ({ time: bar.time, value: bar.volume, color: volumeHex(bar.close >= bar.open ? upVolume : downVolume, volumeOpacity) }));
    const volumeKey=JSON.stringify([upVolume,downVolume,volumeOpacity]);
    if(change.mode==="replace"||previousVolumeStyle.current!==volumeKey)volume.setData(volumeData);else volumeData.slice(change.from).forEach(bar=>volume.update(bar));
    previousVolumeStyle.current=volumeKey;

    if (!initialisedRef.current) {
      const focus=focusTimestamp?clean.findIndex(b=>b.time>=Date.parse(focusTimestamp)/1000):-1;
      const end=focus>=0?Math.min(clean.length,focus+30):clean.length;
      const from = Math.max(0, end - Math.max(60, Number(preferences.chartVisibleBars || initialVisibleBars || 180)));
      try { chart.timeScale().setVisibleLogicalRange({ from, to: end + 5 }); } catch { chart.timeScale().fitContent(); }
      initialisedRef.current = true;
    } else if (change.mode==="replace" && visibleTime?.from != null && visibleTime?.to != null) {
      // Preserve the same market-time window without passing arbitrary timestamps
      // back into Lightweight Charts. A 1m boundary often does not exist on 5m/15m;
      // converting the window to valid logical indexes is substantially more robust
      // and avoids the blank-chart regression introduced in 6.2.3.
      const fromTarget = Number(visibleTime.from);
      const toTarget = Number(visibleTime.to);
      if (Number.isFinite(fromTarget) && Number.isFinite(toTarget)) {
        const firstAtOrAfter = (target) => {
          let lo = 0, hi = clean.length;
          while (lo < hi) { const mid = (lo + hi) >> 1; if (clean[mid].time < target) lo = mid + 1; else hi = mid; }
          return Math.min(clean.length - 1, lo);
        };
        const lastAtOrBefore = (target) => {
          let lo = 0, hi = clean.length;
          while (lo < hi) { const mid = (lo + hi) >> 1; if (clean[mid].time <= target) lo = mid + 1; else hi = mid; }
          return Math.max(0, lo - 1);
        };
        const fromIndex = Math.max(0, lastAtOrBefore(fromTarget));
        const toIndex = Math.max(fromIndex + 1, firstAtOrAfter(toTarget));
        requestAnimationFrame(() => {
          try { chart.timeScale().setVisibleLogicalRange({ from: fromIndex, to: Math.min(clean.length + 5, toIndex + 5) }); }
          catch { chart.timeScale().fitContent(); }
        });
      }
    }
  }, [bars, showVolume, volumeStyle, initialVisibleBars, timeframe, chartState]);

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
  }, [overlays, chartState]);

  return <div className={`relative w-full ${fill || expanded ? "h-full" : ""}`} style={!expanded && !fill ? { height } : undefined}>
    <div ref={ref} className="h-full w-full" />
    {crosshairInfo && <div className="chart-crosshair-readout">
      {crosshairInfo.candle && <span><b>O</b> {Number(crosshairInfo.candle.open).toFixed(2)} <b>H</b> {Number(crosshairInfo.candle.high).toFixed(2)} <b>L</b> {Number(crosshairInfo.candle.low).toFixed(2)} <b>C</b> {Number(crosshairInfo.candle.close).toFixed(2)}</span>}
    </div>}
    {chartState && <DrawingOverlay key={`drawings-${timeframe || "default"}`}
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
