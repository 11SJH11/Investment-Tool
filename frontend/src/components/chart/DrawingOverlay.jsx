import { useEffect, useMemo, useRef, useState } from "react";
import { drawingId } from "./drawingStore";

const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];
const TWO_POINT = new Set(["trend", "rectangle", "arrow", "fib"]);
const THREE_POINT = new Set(["long-position", "short-position"]);
const DRAWING_CLIPBOARD = "ledger.drawingClipboard.v1";

function numTime(value) {
  if (value == null) return null;
  if (typeof value === "number") return value;
  if (typeof value === "object" && value.year) return Math.floor(Date.UTC(value.year, value.month - 1, value.day) / 1000);
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function lineColor(item) { return item.color || "#60a5fa"; }
function fillColor(item, alpha = 0.12) {
  const color = item.color || "#60a5fa";
  if (/^#[0-9a-fA-F]{6}$/.test(color)) {
    const r = parseInt(color.slice(1, 3), 16), g = parseInt(color.slice(3, 5), 16), b = parseInt(color.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }
  return color;
}

function cleanBarTimes(bars) {
  return [...new Set((bars || []).map((bar) => Math.floor(new Date(bar.timestamp).getTime() / 1000)).filter(Number.isFinite))].sort((a, b) => a - b);
}

function medianStep(times) {
  if (times.length < 2) return 60;
  const sample = [];
  for (let i = 1; i < Math.min(times.length, 80); i += 1) {
    const diff = times[i] - times[i - 1];
    if (diff > 0 && diff < 86400 * 4) sample.push(diff);
  }
  if (!sample.length) return 60;
  sample.sort((a, b) => a - b);
  return sample[Math.floor(sample.length / 2)] || 60;
}

function lowerBound(values, target) {
  let lo = 0, hi = values.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (values[mid] < target) lo = mid + 1; else hi = mid;
  }
  return lo;
}

export default function DrawingOverlay({
  chart,
  series,
  container,
  tool = "cursor",
  magnet = "weak",
  bars = [],
  drawings = [],
  selectedId = null,
  onSelect,
  onChange,
  onToolChange,
  onPositionDrawing,
  onUndo,
  onRedo,
  onDeleteSelected,
  drawingMeta = {},
  clampToBars = false,
}) {
  const [draft, setDraft] = useState(null);
  const defaultColor = (typeof localStorage !== "undefined" && localStorage.getItem("ledger.drawingColor")) || "#60a5fa";
  const [renderToken, setRenderToken] = useState(0);
  const [drag, setDrag] = useState(null);
  const svgRef = useRef(null);
  const brushRef = useRef(null);
  const gestureRef = useRef(null);
  const barTimes = useMemo(() => cleanBarTimes(bars), [bars]);
  const barStep = useMemo(() => medianStep(barTimes), [barTimes]);

  useEffect(() => {
    if (!chart || !container) return undefined;
    const redraw = () => setRenderToken((x) => x + 1);
    chart.timeScale().subscribeVisibleLogicalRangeChange(redraw);
    const observer = new ResizeObserver(redraw);
    observer.observe(container);
    return () => {
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(redraw);
      observer.disconnect();
    };
  }, [chart, container]);

  // Lightweight Charts does not expose a price-scale-change subscription. Watch a
  // tiny transform signature so drawings still track price-axis stretching/zooming.
  useEffect(() => {
    if (!chart || !series || !barTimes.length) return undefined;
    let raf = 0;
    let previous = "";
    const watch = () => {
      const first = bars?.[0];
      const last = bars?.[bars.length - 1];
      const signature = [
        chart.timeScale().timeToCoordinate(barTimes[0]),
        chart.timeScale().timeToCoordinate(barTimes[barTimes.length - 1]),
        first ? series.priceToCoordinate(Number(first.low)) : null,
        last ? series.priceToCoordinate(Number(last.high)) : null,
      ].map((x) => x == null ? "n" : Number(x).toFixed(2)).join(":");
      if (signature !== previous) { previous = signature; setRenderToken((x) => x + 1); }
      raf = requestAnimationFrame(watch);
    };
    raf = requestAnimationFrame(watch);
    return () => cancelAnimationFrame(raf);
  }, [chart, series, barTimes, bars]);

  useEffect(() => { setDraft(null); setDrag(null); gestureRef.current = null; }, [tool]);

  const dimensions = useMemo(() => ({ width: container?.clientWidth || 0, height: container?.clientHeight || 0 }), [container, renderToken]);

  const logicalForTime = (time) => {
    if (!chart || !barTimes.length || !Number.isFinite(Number(time))) return null;
    const target = Number(time);
    const index = lowerBound(barTimes, target);
    if (index < barTimes.length && barTimes[index] === target) return index;
    if (index <= 0) return (target - barTimes[0]) / Math.max(1, barStep);
    if (index >= barTimes.length) return (barTimes.length - 1) + (target - barTimes[barTimes.length - 1]) / Math.max(1, barStep);
    const leftTime = barTimes[index - 1], rightTime = barTimes[index];
    const fraction = (target - leftTime) / Math.max(1, rightTime - leftTime);
    return (index - 1) + fraction;
  };

  const timeForLogical = (logical) => {
    if (!barTimes.length || !Number.isFinite(Number(logical))) return null;
    const value = Number(logical);
    if (clampToBars) {
      if (value <= 0) return barTimes[0];
      if (value >= barTimes.length - 1) return barTimes[barTimes.length - 1];
    }
    if (value <= 0) return Math.round(barTimes[0] + value * barStep);
    if (value >= barTimes.length - 1) return Math.round(barTimes[barTimes.length - 1] + (value - (barTimes.length - 1)) * barStep);
    const left = Math.floor(value), right = Math.ceil(value), fraction = value - left;
    return Math.round(barTimes[left] + (barTimes[right] - barTimes[left]) * fraction);
  };

  const toScreen = (point) => {
    if (!chart || !series || !point) return null;
    let x = chart.timeScale().timeToCoordinate(Number(point.time));
    if (x == null) {
      const logical = logicalForTime(Number(point.time));
      if (logical != null) x = chart.timeScale().logicalToCoordinate(logical);
    }
    const y = series.priceToCoordinate(Number(point.price));
    if (x == null || y == null || !Number.isFinite(Number(x)) || !Number.isFinite(Number(y))) return null;
    return { x: Number(x), y: Number(y) };
  };

  const rawMarketPoint = (event) => {
    if (!chart || !series || !container) return null;
    const rect = container.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    let time = numTime(chart.timeScale().coordinateToTime(x));
    if (!Number.isFinite(time)) time = timeForLogical(chart.timeScale().coordinateToLogical(x));
    const price = Number(series.coordinateToPrice(y));
    if (!Number.isFinite(time) || !Number.isFinite(price)) return null;
    return { time, price };
  };

  const snapPoint = (point, event) => {
    if (!point || magnet === "off" || !bars?.length || !container || !chart || !series) return point;
    const rect = container.getBoundingClientRect();
    const px = event.clientX - rect.left;
    let best = null;
    for (const bar of bars) {
      const time = Math.floor(new Date(bar.timestamp).getTime() / 1000);
      let x = chart.timeScale().timeToCoordinate(time);
      if (x == null) {
        const logical = logicalForTime(time);
        if (logical != null) x = chart.timeScale().logicalToCoordinate(logical);
      }
      if (x == null) continue;
      const distance = Math.abs(Number(x) - px);
      if (!best || distance < best.distance) best = { bar, time, x: Number(x), distance };
    }
    if (!best || (magnet === "weak" && best.distance > 14)) return point;
    const candidates = ["open", "high", "low", "close"].map((field) => ({ field, price: Number(best.bar[field]), y: series.priceToCoordinate(Number(best.bar[field])) })).filter((x) => x.y != null);
    const py = event.clientY - rect.top;
    candidates.sort((a, b) => Math.abs(Number(a.y) - py) - Math.abs(Number(b.y) - py));
    if (!candidates.length) return point;
    if (magnet === "weak" && Math.abs(Number(candidates[0].y) - py) > 14) return point;
    return { time: best.time, price: candidates[0].price, snapped: candidates[0].field };
  };

  const eventPoint = (event) => snapPoint(rawMarketPoint(event), event);

  const commit = (item) => {
    if (!item) return;
    const next = [...drawings, { ...item, id: item.id || drawingId(item.type), visible: true, locked: false, color: item.color || defaultColor, lineWidth: item.lineWidth || 2, ...drawingMeta }];
    onChange?.(next);
    onSelect?.(next[next.length - 1].id);
    if (item.type === "long-position" || item.type === "short-position") onPositionDrawing?.(next[next.length - 1]);
    setDraft(null);
    gestureRef.current = null;
    onToolChange?.("select");
  };

  const focusOverlay = () => { try { svgRef.current?.focus?.({ preventScroll: true }); } catch { /* ignored */ } };

  const handlePointerDown = (event) => {
    focusOverlay();
    if (tool === "cursor") return;
    if (tool === "select") { onSelect?.(null); return; }
    const point = eventPoint(event);
    if (!point) return;
    event.preventDefault();

    // Position tools use two gestures: drag Entry→Stop, then click Target.
    if (THREE_POINT.has(tool) && draft?._stage === "target") {
      commit({ ...draft, points: [draft.points[0], draft.points[1], point], _stage: undefined });
      return;
    }

    if (tool === "horizontal" || tool === "horizontal-ray" || tool === "vertical") {
      commit({ type: tool, points: [point] });
      return;
    }
    if (tool === "text") {
      const text = window.prompt("Text note");
      if (text?.trim()) commit({ type: "text", points: [point], text: text.trim() });
      else onToolChange?.("cursor");
      return;
    }
    if (tool === "brush") {
      brushRef.current = { type: "brush", points: [point], color: defaultColor };
      setDraft(brushRef.current);
      try { event.currentTarget.setPointerCapture(event.pointerId); } catch { /* ignored */ }
      return;
    }
    if (TWO_POINT.has(tool)) {
      gestureRef.current = { kind: "two", tool, start: point, startX: event.clientX, startY: event.clientY, pointerId: event.pointerId };
      setDraft({ type: tool, points: [point, point], color: defaultColor, _stage: "drag" });
      try { event.currentTarget.setPointerCapture(event.pointerId); } catch { /* ignored */ }
      return;
    }
    if (THREE_POINT.has(tool)) {
      gestureRef.current = { kind: "position-stop", tool, start: point, startX: event.clientX, startY: event.clientY, pointerId: event.pointerId };
      setDraft({ type: tool, points: [point, point], color: tool === "long-position" ? "#22c55e" : "#ef4444", _stage: "stop" });
      try { event.currentTarget.setPointerCapture(event.pointerId); } catch { /* ignored */ }
    }
  };

  const handlePointerMove = (event) => {
    if (drag) {
      const point = rawMarketPoint(event);
      if (!point) return;
      const item = drawings.find((x) => x.id === drag.id);
      if (!item || item.locked) return;
      let updated;
      if (drag.kind === "point") {
        updated = { ...item, points: item.points.map((p, i) => i === drag.index ? { ...point } : p) };
      } else {
        const originMarket = drag.originMarket || drag.market;
        const originPoints = drag.originPoints || item.points;
        const dt = point.time - originMarket.time;
        const dp = point.price - originMarket.price;
        updated = { ...item, points: originPoints.map((p) => ({ ...p, time: Number(p.time) + dt, price: Number(p.price) + dp })) };
      }
      onChange?.(drawings.map((x) => x.id === item.id ? updated : x), { transient: true });
      return;
    }
    if (tool === "brush" && brushRef.current && (event.buttons & 1)) {
      const point = eventPoint(event);
      if (!point) return;
      const points = [...brushRef.current.points, point];
      brushRef.current = { ...brushRef.current, points };
      setDraft(brushRef.current);
      return;
    }
    const gesture = gestureRef.current;
    if (gesture) {
      const point = eventPoint(event);
      if (!point) return;
      if (gesture.kind === "two") setDraft((current) => current ? { ...current, points: [gesture.start, point] } : current);
      if (gesture.kind === "position-stop") setDraft((current) => current ? { ...current, points: [gesture.start, point] } : current);
      return;
    }
    if (THREE_POINT.has(tool) && draft?._stage === "target") {
      const point = eventPoint(event);
      if (point) setDraft((current) => current ? { ...current, points: [current.points[0], current.points[1], point] } : current);
    }
  };

  const handlePointerUp = (event) => {
    if (drag) { setDrag(null); return; }
    if (tool === "brush" && brushRef.current) {
      const item = brushRef.current;
      brushRef.current = null;
      if (item.points.length > 1) commit(item); else setDraft(null);
      return;
    }
    const gesture = gestureRef.current;
    if (!gesture) return;
    const point = eventPoint(event) || gesture.start;
    const moved = Math.hypot(event.clientX - gesture.startX, event.clientY - gesture.startY) >= 3;
    gestureRef.current = null;
    if (gesture.kind === "two") {
      if (moved) commit({ type: gesture.tool, points: [gesture.start, point], color: defaultColor });
      else setDraft(null);
      return;
    }
    if (gesture.kind === "position-stop") {
      if (!moved) { setDraft(null); return; }
      setDraft({
        type: gesture.tool,
        points: [gesture.start, point, point],
        color: gesture.tool === "long-position" ? "#22c55e" : "#ef4444",
        _stage: "target",
      });
    }
  };

  const startMove = (event, item, kind = "whole", index = null) => {
    if (tool !== "select" || item.locked) return;
    focusOverlay();
    event.preventDefault(); event.stopPropagation();
    const market = rawMarketPoint(event);
    if (!market) return;
    onSelect?.(item.id);
    onChange?.(drawings, { checkpoint: true });
    setDrag({ id: item.id, kind, index, market, originMarket: market, originPoints: item.points.map((p) => ({ ...p })) });
    try { svgRef.current?.setPointerCapture?.(event.pointerId); } catch { /* ignored */ }
  };

  const copySelected = () => {
    const item = drawings.find((x) => x.id === selectedId);
    if (!item) return;
    try { localStorage.setItem(DRAWING_CLIPBOARD, JSON.stringify(item)); } catch { /* ignored */ }
  };

  const pasteDrawing = () => {
    let copied = null;
    try { copied = JSON.parse(localStorage.getItem(DRAWING_CLIPBOARD) || "null"); } catch { copied = null; }
    if (!copied?.type || !Array.isArray(copied.points)) return;
    const basePrice = Number(copied.points[0]?.price || 0);
    const dt = Math.max(1, barStep * 2);
    const dp = Math.abs(basePrice) * 0.002 || 0.1;
    const points = copied.points.map((point) => ({
      ...point,
      time: Number(point.time) + (copied.type === "horizontal" ? 0 : dt),
      price: Number(point.price) + (copied.type === "vertical" ? 0 : dp),
    }));
    const item = { ...copied, id: drawingId(copied.type), points, locked: false, ...drawingMeta };
    const next = [...drawings, item];
    onChange?.(next);
    onSelect?.(item.id);
    onToolChange?.("select");
  };

  const handleKeyDown = (event) => {
    const modifier = event.ctrlKey || event.metaKey;
    const key = String(event.key || "").toLowerCase();
    if (modifier && key === "z") {
      event.preventDefault();
      if (event.shiftKey) onRedo?.(); else onUndo?.();
      return;
    }
    if (modifier && key === "y") { event.preventDefault(); onRedo?.(); return; }
    if (modifier && key === "c") { event.preventDefault(); copySelected(); return; }
    if (modifier && key === "v") { event.preventDefault(); pasteDrawing(); return; }
    if ((event.key === "Delete" || event.key === "Backspace") && selectedId) {
      event.preventDefault(); onDeleteSelected?.(selectedId);
    }
  };

  const display = [...drawings.filter((x) => x.visible !== false), ...(draft ? [{ ...draft, id: "__draft__", visible: true }] : [])];
  const interactive = tool !== "cursor";
  return <svg
    ref={svgRef}
    tabIndex={0}
    aria-label="Chart drawing layer"
    className="chart-drawing-overlay"
    width={dimensions.width}
    height={dimensions.height}
    style={{ pointerEvents: interactive ? "auto" : "none", outline: "none" }}
    onPointerDown={handlePointerDown}
    onPointerMove={handlePointerMove}
    onPointerUp={handlePointerUp}
    onPointerCancel={handlePointerUp}
    onKeyDown={handleKeyDown}
  >
    <defs><marker id="ledger-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="context-stroke" /></marker></defs>
    {display.map((item) => <Drawing key={item.id} item={item} toScreen={toScreen} width={dimensions.width} height={dimensions.height} selected={selectedId === item.id} selectable={tool === "select"} onMove={(e) => startMove(e, item)} onPointMove={(e, index) => startMove(e, item, "point", index)} />)}
  </svg>;
}

function Drawing({ item, toScreen, width, height, selected, selectable, onMove, onPointMove }) {
  const points = (item.points || []).map(toScreen);
  const color = lineColor(item); const strokeWidth = Number(item.lineWidth || 2);
  const common = { stroke: color, strokeWidth, fill: "none", vectorEffect: "non-scaling-stroke", style: { pointerEvents: selectable ? "stroke" : "none", cursor: selectable ? "move" : "default" }, onPointerDown: onMove };
  const handles = selected && selectable ? points.map((p, index) => p && <circle key={index} cx={p.x} cy={p.y} r="5" fill="#fff" stroke={color} strokeWidth="2" style={{ pointerEvents: "all", cursor: "grab" }} onPointerDown={(e) => onPointMove(e, index)} />) : null;

  if (item.type === "horizontal" || item.type === "horizontal-ray") {
    const p = points[0]; if (!p) return null; const x1 = item.type === "horizontal-ray" ? Math.max(0, p.x) : 0;
    return <g><line x1={x1} y1={p.y} x2={width} y2={p.y} {...common}/>{handles}</g>;
  }
  if (item.type === "vertical") { const p = points[0]; if (!p) return null; return <g><line x1={p.x} y1="0" x2={p.x} y2={height} {...common}/>{handles}</g>; }
  if (item.type === "trend" || item.type === "arrow") {
    const [a,b]=points; if(!a||!b)return draftHint(item, points, color);
    return <g><line x1={a.x} y1={a.y} x2={b.x} y2={b.y} {...common} markerEnd={item.type === "arrow" ? "url(#ledger-arrow)" : undefined}/>{handles}</g>;
  }
  if (item.type === "rectangle") {
    const [a,b]=points; if(!a||!b)return draftHint(item, points, color); const x=Math.min(a.x,b.x), y=Math.min(a.y,b.y), w=Math.abs(b.x-a.x), h=Math.abs(b.y-a.y);
    return <g><rect x={x} y={y} width={w} height={h} stroke={color} strokeWidth={strokeWidth} fill={fillColor(item,.12)} vectorEffect="non-scaling-stroke" style={{pointerEvents:selectable?"all":"none",cursor:selectable?"move":"default"}} onPointerDown={onMove}/>{handles}</g>;
  }
  if (item.type === "brush") {
    const clean=points.filter(Boolean); if(clean.length<2)return draftHint(item, points, color); return <g><polyline points={clean.map(p=>`${p.x},${p.y}`).join(" ")} strokeLinecap="round" strokeLinejoin="round" {...common}/>{handles}</g>;
  }
  if (item.type === "text") {
    const p=points[0]; if(!p)return null; return <g style={{pointerEvents:selectable?"all":"none",cursor:selectable?"move":"default"}} onPointerDown={onMove}><rect x={p.x-4} y={p.y-18} width={Math.max(46,(item.text||"").length*7+8)} height="22" rx="4" fill="rgba(17,24,39,.82)"/><text x={p.x} y={p.y-3} fill={color} fontSize="12" fontWeight="600">{item.text}</text>{handles}</g>;
  }
  if (item.type === "fib") {
    const [a,b]=points; if(!a||!b)return draftHint(item, points, color); const priceA=Number(item.points[0].price), priceB=Number(item.points[1].price); const x1=Math.min(a.x,b.x), x2=Math.max(a.x,b.x);
    return <g onPointerDown={onMove} style={{pointerEvents:selectable?"all":"none",cursor:selectable?"move":"default"}}>{FIB_LEVELS.map(level=>{const price=priceA+(priceB-priceA)*level; const y=a.y+(b.y-a.y)*level; return <g key={level}><line x1={x1} y1={y} x2={x2} y2={y} stroke={color} strokeWidth="1" opacity={level===0||level===1?1:.75}/><text x={x2+5} y={y+4} fill={color} fontSize="10">{level} · {price.toFixed(2)}</text></g>})}{handles}</g>;
  }
  if (item.type === "long-position" || item.type === "short-position") {
    const entry=points[0], stop=points[1], target=points[2];
    if (!entry) return null;
    if (!stop) return draftHint(item, points, color, "Drag to set stop");
    const direction=item.type==="long-position"?"long":"short";
    const x1=Math.min(entry.x,stop.x,target?.x ?? stop.x); const x2=Math.max(x1+120,entry.x,stop.x,target?.x ?? stop.x);
    const riskTop=Math.min(entry.y,stop.y), riskHeight=Math.abs(stop.y-entry.y);
    const entryPrice=Number(item.points[0].price), stopPrice=Number(item.points[1].price); const risk=Math.abs(entryPrice-stopPrice);
    const rewardTop=target?Math.min(entry.y,target.y):entry.y; const rewardHeight=target?Math.abs(target.y-entry.y):0;
    const targetPrice=target?Number(item.points[2].price):null; const rr=risk&&targetPrice!=null?Math.abs(targetPrice-entryPrice)/risk:null;
    return <g onPointerDown={onMove} style={{pointerEvents:selectable?"all":"none",cursor:selectable?"move":"default"}}>
      {target&&<rect x={x1} y={rewardTop} width={x2-x1} height={rewardHeight} fill="rgba(34,197,94,.16)"/>}
      <rect x={x1} y={riskTop} width={x2-x1} height={riskHeight} fill="rgba(239,68,68,.16)"/>
      <line x1={x1} y1={entry.y} x2={x2} y2={entry.y} stroke="#e5e7eb" strokeWidth="1.5"/>
      <line x1={x1} y1={stop.y} x2={x2} y2={stop.y} stroke="#ef4444" strokeWidth="1.5"/>
      {target&&<line x1={x1} y1={target.y} x2={x2} y2={target.y} stroke="#22c55e" strokeWidth="1.5"/>}
      <text x={x1+6} y={entry.y-6} fill="#e5e7eb" fontSize="10">{direction.toUpperCase()} · {item._stage === "target" ? "click target" : `R:R ${rr?rr.toFixed(2):"—"}`}</text>
      {handles}
    </g>;
  }
  return null;
}

function draftHint(item, points, color, text = "Drag to size") {
  if (item.id !== "__draft__") return null;
  const p = points.find(Boolean);
  if (!p) return null;
  return <g><circle cx={p.x} cy={p.y} r="4.5" fill={color}/><text x={p.x+7} y={p.y-7} fill={color} fontSize="10">{text}</text></g>;
}
