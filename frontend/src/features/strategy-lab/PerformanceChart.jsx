import { useEffect, useRef } from "react";
import { ColorType, LineSeries, createChart, createSeriesMarkers } from "lightweight-charts";
import { resolvedZone } from "../../utils/timezones";

function timeLabel(seconds, zone) {
  const date = new Date(Number(seconds) * 1000);
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: resolvedZone(zone),
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).format(date);
}
function dateTick(seconds, zone) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: resolvedZone(zone), day: "2-digit", month: "short",
  }).format(new Date(Number(seconds) * 1000));
}
function money(value) {
  return Intl.NumberFormat("en-GB", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(Number(value || 0));
}
function modeValue(point, mode) {
  if (mode === "drawdown") return Number(point.drawdown_pct);
  if (mode === "return") return Number(point.return_pct);
  if (mode === "r") return Number(point.cumulative_r);
  return Number(point.equity);
}
function formatted(value, mode) {
  if (mode === "equity") return money(value);
  if (mode === "r") return `${Number(value) >= 0 ? "+" : ""}${Number(value).toFixed(2)}R`;
  return `${Number(value) >= 0 && mode === "return" ? "+" : ""}${Number(value).toFixed(2)}%`;
}

export default function PerformanceChart({
  points = [], startingBalance = 0, mode = "equity", expanded = false,
  timeZone = "America/New_York", onTradeSelect = null,
}) {
  const containerRef = useRef(null);
  const tooltipRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current || !points.length) return undefined;
    const chart = createChart(containerRef.current, {
      autoSize: true,
      height: expanded ? Math.max(620, window.innerHeight - 180) : (mode === "drawdown" ? 240 : 360),
      layout: { background: { type: ColorType.Solid, color: "#fafaf9" }, textColor: "#57534e" },
      grid: { vertLines: { color: "#e7e5e4" }, horzLines: { color: "#e7e5e4" } },
      rightPriceScale: { borderColor: "#d6d3d1" },
      timeScale: {
        borderColor: "#d6d3d1", timeVisible: true, secondsVisible: false,
        tickMarkFormatter: (time) => dateTick(time, timeZone),
      },
      localization: {
        timeFormatter: (time) => timeLabel(time, timeZone),
        priceFormatter: (value) => formatted(value, mode),
      },
      crosshair: { vertLine: { color: "#78716c" }, horzLine: { color: "#78716c" } },
    });
    const series = chart.addSeries(LineSeries, {
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      priceFormat: mode === "equity"
        ? { type: "price", precision: 2, minMove: 0.01 }
        : { type: "custom", minMove: 0.01, formatter: (value) => formatted(value, mode) },
    });

    const seen = new Set();
    const clean = points.map((point) => ({
      time: Math.floor(new Date(point.timestamp).getTime() / 1000),
      value: modeValue(point, mode),
      original: point,
    })).filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value) && !seen.has(point.time) && seen.add(point.time));
    series.setData(clean.map(({ time, value }) => ({ time, value })));

    if (mode === "equity" && Number.isFinite(Number(startingBalance))) {
      series.createPriceLine({
        price: Number(startingBalance), title: "Starting balance", lineWidth: 1, lineStyle: 2, axisLabelVisible: true,
      });
    }
    if ((mode === "return" || mode === "r" || mode === "drawdown")) {
      series.createPriceLine({ price: 0, title: "0", lineWidth: 1, lineStyle: 2, axisLabelVisible: false });
    }

    const byTime = new Map(clean.map((point) => [point.time, point.original]));
    const markerTradeById = new Map();
    if (onTradeSelect) {
      const markers = [];
      clean.forEach((point, pointIndex) => {
        (point.original?.closed_trades || []).forEach((trade, tradeIndex) => {
          const markerId = `trade-${pointIndex}-${tradeIndex}`;
          markerTradeById.set(markerId, trade);
          markers.push({
            id: markerId, time: point.time, position: "aboveBar", shape: "circle",
            color: Number(trade.r_multiple || 0) >= 0 ? "#16a34a" : "#dc2626",
          });
        });
      });
      if (markers.length) createSeriesMarkers(series, markers);
    }
    chart.subscribeCrosshairMove((param) => {
      const tooltip = tooltipRef.current;
      if (!tooltip || !param?.time || !param?.point) {
        if (tooltip) tooltip.style.display = "none";
        return;
      }
      const time = Number(param.time);
      const point = byTime.get(time);
      const datum = param.seriesData?.get(series);
      if (!datum || !point) { tooltip.style.display = "none"; return; }
      const lines = [
        timeLabel(time, timeZone),
        `Equity: ${money(point.equity)}`,
        `Return: ${Number(point.return_pct || 0) >= 0 ? "+" : ""}${Number(point.return_pct || 0).toFixed(2)}%`,
        `Cumulative R: ${Number(point.cumulative_r || 0) >= 0 ? "+" : ""}${Number(point.cumulative_r || 0).toFixed(2)}R`,
        `Drawdown: ${Number(point.drawdown_pct || 0).toFixed(2)}%`,
      ];
      if (Number(point.realized_pnl || 0) !== 0) lines.push(`Realised here: ${money(point.realized_pnl)}`);
      for (const trade of point.closed_trades || []) {
        lines.push(`${trade.symbol} ${trade.direction} · ${String(trade.exit_reason).replaceAll("_", " ")} · ${Number(trade.r_multiple || 0) >= 0 ? "+" : ""}${Number(trade.r_multiple || 0).toFixed(2)}R · ${money(trade.net_pnl)}`);
      }
      if ((point.closed_trades || []).length && onTradeSelect) lines.push("Click to audit closed trade");
      tooltip.textContent = lines.join("\n");
      tooltip.style.display = "block";
      const width = containerRef.current.clientWidth;
      tooltip.style.left = `${Math.min(Math.max(8, param.point.x + 14), Math.max(8, width - 300))}px`;
      tooltip.style.top = `${Math.max(8, param.point.y - 30)}px`;
    });
    if (onTradeSelect) {
      chart.subscribeClick((param) => {
        const markerId = param?.hoveredObjectId;
        const trade = markerId ? markerTradeById.get(String(markerId)) : null;
        if (trade) onTradeSelect(trade);
      });
    }
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [points, startingBalance, mode, expanded, timeZone, onTradeSelect]);

  return <div className="relative mt-4">
    <div ref={containerRef} className={expanded ? "h-[calc(100vh-180px)] w-full" : (mode === "drawdown" ? "h-[240px] w-full" : "h-[360px] w-full")} />
    <div ref={tooltipRef} className="pointer-events-none absolute hidden max-w-[300px] whitespace-pre-line rounded-md border border-stone-300 bg-white/95 px-3 py-2 text-xs leading-5 text-stone-700 shadow-lg" />
  </div>;
}
