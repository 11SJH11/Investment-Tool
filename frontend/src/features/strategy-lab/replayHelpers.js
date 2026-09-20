import {resolvedZone} from "../../utils/timezones.js";
export const INDICATOR_COLORS = ["#60a5fa", "#f59e0b", "#a78bfa", "#22c55e", "#f43f5e", "#06b6d4", "#e879f9", "#84cc16", "#fb7185", "#38bdf8", "#facc15", "#c084fc"];
let indicatorSequence = 0;

export function daysAgo(days) { const d = new Date(); d.setDate(d.getDate() - days); return d.toISOString().slice(0, 10); }
export function addDays(value, days) { const d = new Date(`${value}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + days); return d.toISOString().slice(0, 10); }
export function money(value) { return value == null || !Number.isFinite(Number(value)) ? "—" : `$${Number(value).toFixed(2)}`; }
export function fmt(value, zone) { return value ? new Intl.DateTimeFormat("en-GB", { timeZone: resolvedZone(zone), dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—"; }
export function nyDate(value) { return value ? new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value)) : ""; }
export function currentValue(indicator, lastTimestamp) {
  const eligible = (indicator?.values || []).filter((point) => new Date(point.timestamp).getTime() <= new Date(lastTimestamp).getTime());
  return eligible.length ? Number(eligible[eligible.length - 1].value) : null;
}
export function countThroughTimestamp(bars, timestamp, fallback = 1) {
  if (!timestamp || !Array.isArray(bars) || !bars.length) return Math.min(Math.max(1, Number(fallback || 1)), bars?.length || 1);
  const cutoff = new Date(timestamp).getTime();
  const count = bars.reduce((total, bar) => total + (new Date(bar.timestamp).getTime() <= cutoff ? 1 : 0), 0);
  return Math.min(Math.max(1, count || Number(fallback || 1)), bars.length);
}
export function indicatorRequestSignature(item, dataset, symbol, timeframe, session, replayDate, replayEndDate, startTime, context) {
  return JSON.stringify({
    id: item.id, key: item.key, params: item.params || {},
    symbol, timeframe, session, replayDate, replayEndDate, startTime,
    contextBars: context.contextBars, contextDays: context.contextDays,
    frontier: dataset?.frontier, datasetCount: dataset?.count, sourceTimeframe: dataset?.source_timeframe, aggregation: dataset?.aggregation,
  });
}
export function contextArgs(mode, customBars) {
  if (mode === "1d") return { contextDays: 1, contextBars: 0 };
  if (mode === "5d") return { contextDays: 8, contextBars: 0 };
  if (mode === "1m") return { contextDays: 31, contextBars: 0 };
  if (mode === "3m") return { contextDays: 93, contextBars: 0 };
  return { contextDays: null, contextBars: Math.max(0, Number(customBars || 0)) };
}
export function makeIndicator(spec, colorIndex) {
  return {
    id: `indicator-${Date.now()}-${indicatorSequence++}`,
    key: spec.key,
    params: { ...(spec.defaults || {}) },
    visible: true,
    color: INDICATOR_COLORS[colorIndex % INDICATOR_COLORS.length],
    lineWidth: 2,
    ...(spec.key === "volume" ? { upColor: "#34d399", downColor: "#f87171", volumeOpacity: 0.28 } : {}),
  };
}
export function plannedMetrics(position) {
  if (!position) return { risk: null, rr: null };
  const entry = Number(position.entry_price); const qty = Number(position.quantity || 0);
  const stop = position.stop_loss == null ? null : Number(position.stop_loss);
  const target = position.take_profit == null ? null : Number(position.take_profit);
  const perShareRisk = stop == null ? null : Math.abs(entry - stop);
  return {
    risk: perShareRisk == null ? null : perShareRisk * qty * (position.contract_multiplier || 1),
    rr: perShareRisk && target != null ? Math.abs(target - entry) / perShareRisk : null,
  };
}

