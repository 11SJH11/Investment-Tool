import { useEffect, useMemo, useRef, useState } from "react";
import { drawingId } from "./drawingStore";

export const DEFAULT_FIB_LEVELS = [
  { value: 0, visible: true }, { value: 0.236, visible: true }, { value: 0.382, visible: true },
  { value: 0.5, visible: true }, { value: 0.618, visible: true }, { value: 0.786, visible: true }, { value: 1, visible: true },
];
const TWO_POINT = new Set(["trend", "rectangle", "arrow", "fib"]);
const POSITION = new Set(["long-position", "short-position"]);
const DRAWING_CLIPBOARD = "ledger.drawingClipboard.v1";

function numTime(value) {
  if (value == null) return null;
  if (typeof value === "number") return value;
  if (typeof value === "object" && value.year) return Math.floor(Date.UTC(value.year, value.month - 1, value.day) / 1000);
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}
function lineColor(item) { return item.color || "#60a5fa"; }
function rgba(hex, alpha = 0.12) {
  const color = hex || "#60a5fa";
  if (/^#[0-9a-fA-F]{6}$/.test(color)) {
    const r = parseInt(color.slice(1, 3), 16), g = parseInt(color.slice(3, 5), 16), b = parseInt(color.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }
  return color;
}
function dash(item) {
  if (item.lineStyle === "dashed") return "7 5";
  if (item.lineStyle === "dotted") return "2 4";
  return undefined;
}
function cleanBarTimes(bars) {
  return [...new Set((bars || []).map((bar) => Math.floor(new Date(bar.timestamp).getTime() / 1000)).filter(Number.isFinite))].sort((a, b) => a - b);
}
function medianStep(times) {
  if (times.length < 2) return 60;
  const sample = [];
  for (let i = 1; i < Math.min(times.length, 80); i += 1) {
    const diff = times[i] - times[i - 1]; if (diff > 0 && diff < 86400 * 4) sample.push(diff);
  }
  if (!sample.length) return 60;
  sample.sort((a, b) => a - b); return sample[Math.floor(sample.length / 2)] || 60;
}
function lowerBound(values, target) {
  let lo = 0, hi = values.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (values[mid] < target) lo = mid + 1; else hi = mid; }
  return lo;
}
function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }
function drawingDefaults(type, color, point, barStep) {
  const base = { color, lineWidth: 2, lineStyle: "solid", opacity: 1 };
  if (type === "rectangle") return { ...base, fillColor: color, fillOpacity: 0.12 };
  if (type === "fib") return { ...base, fibLevels: DEFAULT_FIB_LEVELS.map((x) => ({ ...x, color })), fibFillColor: color, fibFillOpacity: 0.04, showFibPrices: true };
  if (type === "brush") return { ...base, lineWidth: 3 };
  if (type === "text") return { ...base, fontSize: 12, backgroundColor: "#111827", backgroundOpacity: 0.82 };
  if (POSITION.has(type)) {
    const direction = type === "long-position" ? 1 : -1;
    const risk = Math.max(Math.abs(Number(point?.price || 0)) * 0.005, 0.01);
    const entry = { ...point };
    const stop = { ...point, price: Number(point.price) - direction * risk };
    const target = { ...point, price: Number(point.price) + direction * risk * 2 };
    const end = { ...point, time: Number(point.time) + Math.max(1, barStep) * 12 };
    return { ...base, points: [entry, stop, target, end], profitColor: "#22c55e", lossColor: "#ef4444", fillOpacity: 0.16 };
  }
  return base;
}

export default function DrawingOverlay({
  chart, series, container, tool = "cursor", magnet = "weak", bars = [], drawings = [], selectedId = null,
  onSelect, onChange, onToolChange, onPositionDrawing, onUndo, onRedo, onDeleteSelected, drawingMeta = {}, clampToBars = false,
}) {
  const [draft, setDraft] = useState(null);
  const defaultColor = (typeof localStorage !== "undefined" && localStorage.getItem("ledger.drawingColor")) || "#60a5fa";
  const [renderToken, setRenderToken] = useState(0);
  const [drag, setDrag] = useState(null);
  const svgRef = useRef(null); const brushRef = useRef(null); const gestureRef = useRef(null); const brushScreenRef = useRef(null);
  const barTimes = useMemo(() => cleanBarTimes(bars), [bars]);
  const barStep = useMemo(() => medianStep(barTimes), [barTimes]);

  useEffect(() => {
    if (!chart || !container) return undefined;
    const redraw = () => setRenderToken((x) => x + 1);
    chart.timeScale().subscribeVisibleLogicalRangeChange(redraw);
    const observer = new ResizeObserver(redraw); observer.observe(container);
    return () => { chart.timeScale().unsubscribeVisibleLogicalRangeChange(redraw); observer.disconnect(); };
  }, [chart, container]);

  useEffect(() => {
    if (!chart || !series || !barTimes.length) return undefined;
    let raf = 0; let previous = "";
    const watch = () => {
      const first = bars?.[0], last = bars?.[bars.length - 1];
      const signature = [chart.timeScale().timeToCoordinate(barTimes[0]), chart.timeScale().timeToCoordinate(barTimes[barTimes.length - 1]), first ? series.priceToCoordinate(Number(first.low)) : null, last ? series.priceToCoordinate(Number(last.high)) : null]
        .map((x) => x == null ? "n" : Number(x).toFixed(2)).join(":");
      if (signature !== previous) { previous = signature; setRenderToken((x) => x + 1); }
      raf = requestAnimationFrame(watch);
    };
    raf = requestAnimationFrame(watch); return () => cancelAnimationFrame(raf);
  }, [chart, series, barTimes, bars]);

  useEffect(() => { setDraft(null); setDrag(null); gestureRef.current = null; brushRef.current = null; brushScreenRef.current = null; }, [tool]);
  const dimensions = useMemo(() => ({ width: container?.clientWidth || 0, height: container?.clientHeight || 0 }), [container, renderToken]);

  const logicalForTime = (time) => {
    if (!chart || !barTimes.length || !Number.isFinite(Number(time))) return null;
    const target = Number(time), index = lowerBound(barTimes, target);
    if (index < barTimes.length && barTimes[index] === target) return index;
    if (index <= 0) return (target - barTimes[0]) / Math.max(1, barStep);
    if (index >= barTimes.length) return (barTimes.length - 1) + (target - barTimes[barTimes.length - 1]) / Math.max(1, barStep);
    const leftTime = barTimes[index - 1], rightTime = barTimes[index];
    return (index - 1) + (target - leftTime) / Math.max(1, rightTime - leftTime);
  };
  const timeForLogical = (logical) => {
    if (!barTimes.length || !Number.isFinite(Number(logical))) return null;
    const value = Number(logical);
    if (clampToBars) { if (value <= 0) return barTimes[0]; if (value >= barTimes.length - 1) return barTimes[barTimes.length - 1]; }
    if (value <= 0) return Math.round(barTimes[0] + value * barStep);
    if (value >= barTimes.length - 1) return Math.round(barTimes[barTimes.length - 1] + (value - (barTimes.length - 1)) * barStep);
    const left = Math.floor(value), right = Math.ceil(value), fraction = value - left;
    return Math.round(barTimes[left] + (barTimes[right] - barTimes[left]) * fraction);
  };
  const toScreen = (point) => {
    if (!chart || !series || !point) return null;
    // Always project stored market timestamps through the current bar lattice first.
    // This keeps non-exact timestamps (for example a 10:17 anchor on a 15m chart)
    // stable and avoids Lightweight Charts treating synthetic timestamps inconsistently.
    let x = null;
    const logical = logicalForTime(Number(point.time));
    if (logical != null) x = chart.timeScale().logicalToCoordinate(logical);
    if (x == null) x = chart.timeScale().timeToCoordinate(Number(point.time));
    const y = series.priceToCoordinate(Number(point.price));
    if (x == null || y == null || !Number.isFinite(Number(x)) || !Number.isFinite(Number(y))) return null;
    return { x: Number(x), y: Number(y) };
  };
  const rawMarketPoint = (event) => {
    if (!chart || !series || !container) return null;
    const rect = container.getBoundingClientRect(), x = event.clientX - rect.left, y = event.clientY - rect.top;
    // Derive time from logical chart position first. The visual chart is bar-spaced,
    // not calendar-time-spaced, so this is the reliable inverse of toScreen().
    const logical = chart.timeScale().coordinateToLogical(x);
    let time = timeForLogical(logical);
    if (!Number.isFinite(time)) time = numTime(chart.timeScale().coordinateToTime(x));
    const price = Number(series.coordinateToPrice(y));
    return Number.isFinite(time) && Number.isFinite(price) ? { time, price } : null;
  };
  const snapPoint = (point, event) => {
    if (!point || magnet === "off" || !bars?.length || !container || !chart || !series) return point;
    const rect = container.getBoundingClientRect(), px = event.clientX - rect.left; let best = null;
    for (const bar of bars) {
      const time = Math.floor(new Date(bar.timestamp).getTime() / 1000); let x = chart.timeScale().timeToCoordinate(time);
      if (x == null) { const logical = logicalForTime(time); if (logical != null) x = chart.timeScale().logicalToCoordinate(logical); }
      if (x == null) continue; const distance = Math.abs(Number(x) - px);
      if (!best || distance < best.distance) best = { bar, time, distance };
    }
    if (!best || (magnet === "weak" && best.distance > 14)) return point;
    const candidates = ["open", "high", "low", "close"].map((field) => ({ field, price: Number(best.bar[field]), y: series.priceToCoordinate(Number(best.bar[field])) })).filter((x) => x.y != null);
    const py = event.clientY - rect.top; candidates.sort((a, b) => Math.abs(Number(a.y) - py) - Math.abs(Number(b.y) - py));
    if (!candidates.length || (magnet === "weak" && Math.abs(Number(candidates[0].y) - py) > 14)) return point;
    return { time: best.time, price: candidates[0].price, snapped: candidates[0].field };
  };
  const eventPoint = (event) => snapPoint(rawMarketPoint(event), event);

  const commit = (item) => {
    if (!item) return;
    const defaults = drawingDefaults(item.type, item.color || defaultColor, item.points?.[0], barStep);
    const nextItem = { ...defaults, ...item, id: item.id || drawingId(item.type), visible: true, locked: false, ...drawingMeta };
    const next = [...drawings, nextItem]; onChange?.(next); onSelect?.(nextItem.id);
    if (POSITION.has(item.type)) onPositionDrawing?.(nextItem);
    setDraft(null); gestureRef.current = null; onToolChange?.("cursor");
  };
  const focusOverlay = () => { try { svgRef.current?.focus?.({ preventScroll: true }); } catch { /* ignored */ } };

  const handlePointerDown = (event) => {
    if (tool === "cursor") return;
    focusOverlay(); const point = eventPoint(event); if (!point) return; event.preventDefault();
    if (tool === "horizontal" || tool === "horizontal-ray" || tool === "vertical") { commit({ type: tool, points: [point] }); return; }
    if (tool === "text") {
      const text = window.prompt("Text note");
      if (text?.trim()) commit({ type: "text", points: [point], text: text.trim() }); else onToolChange?.("cursor");
      return;
    }
    if (tool === "brush") {
      brushRef.current = { type: "brush", points: [point], ...drawingDefaults("brush", defaultColor, point, barStep) };
      brushScreenRef.current = { x: event.clientX, y: event.clientY }; setDraft(brushRef.current);
      try { event.currentTarget.setPointerCapture(event.pointerId); } catch { /* ignored */ } return;
    }
    if (POSITION.has(tool)) {
      const defaults = drawingDefaults(tool, tool === "long-position" ? "#22c55e" : "#ef4444", point, barStep);
      commit({ type: tool, ...defaults }); return;
    }
    if (TWO_POINT.has(tool)) {
      gestureRef.current = { kind: "two", tool, start: point, startX: event.clientX, startY: event.clientY, pointerId: event.pointerId };
      setDraft({ type: tool, points: [point, point], ...drawingDefaults(tool, defaultColor, point, barStep), _stage: "drag" });
      try { event.currentTarget.setPointerCapture(event.pointerId); } catch { /* ignored */ }
    }
  };

  const handlePointerMove = (event) => {
    if (drag) {
      const point = rawMarketPoint(event); if (!point) return;
      const item = drawings.find((x) => x.id === drag.id); if (!item || item.locked || item.type === "brush") return;
      let updated;
      if (drag.kind === "point") {
        if (POSITION.has(item.type)) {
          const pts = item.points.map((p) => ({ ...p }));
          if (drag.index === 0) {
            // Entry is the left/start anchor. Moving it horizontally moves the three
            // price anchors together; moving it vertically changes entry only.
            const oldTime = Number(pts[0].time), dt = Number(point.time) - oldTime;
            pts[0] = { ...pts[0], time: Number(point.time), price: Number(point.price) };
            pts[1] = { ...pts[1], time: Number(pts[1].time) + dt };
            pts[2] = { ...pts[2], time: Number(pts[2].time) + dt };
            if (Number(pts[3]?.time) <= Number(pts[0].time)) pts[3] = { ...(pts[3] || pts[0]), time: Number(pts[0].time) + Math.max(1, barStep) * 12, price: Number(pts[0].price) };
          } else if (drag.index === 1 || drag.index === 2) {
            // Stop/target resize vertically only. Tiny accidental horizontal mouse
            // movement must never shear the position box or send an anchor left.
            pts[drag.index] = { ...pts[drag.index], time: Number(pts[0].time), price: Number(point.price) };
          } else if (drag.index === 3) {
            // Width handle is horizontal only and is constrained to the right.
            pts[3] = { ...pts[3], time: Math.max(Number(point.time), Number(pts[0].time) + Math.max(1, barStep) * 2), price: Number(pts[0].price) };
          }
          updated = { ...item, points: pts };
        } else {
          updated = { ...item, points: item.points.map((p, i) => i === drag.index ? { ...point } : p) };
        }
      } else {
        const dt = point.time - drag.originMarket.time, dp = point.price - drag.originMarket.price;
        updated = { ...item, points: drag.originPoints.map((p) => ({ ...p, time: Number(p.time) + dt, price: Number(p.price) + dp })) };
      }
      onChange?.(drawings.map((x) => x.id === item.id ? updated : x), { transient: true });
      if (POSITION.has(item.type)) onPositionDrawing?.(updated);
      return;
    }
    if (tool === "brush" && brushRef.current && (event.buttons & 1)) {
      const previous = brushScreenRef.current; const distance = previous ? Math.hypot(event.clientX - previous.x, event.clientY - previous.y) : 999;
      if (distance < 5) return;
      const point = eventPoint(event); if (!point) return;
      brushScreenRef.current = { x: event.clientX, y: event.clientY };
      brushRef.current = { ...brushRef.current, points: [...brushRef.current.points, point] }; setDraft(brushRef.current); return;
    }
    const gesture = gestureRef.current;
    if (gesture) { const point = eventPoint(event); if (point && gesture.kind === "two") setDraft((current) => current ? { ...current, points: [gesture.start, point] } : current); }
  };
  const handlePointerUp = (event) => {
    if (drag) { setDrag(null); return; }
    if (tool === "brush" && brushRef.current) {
      const item = brushRef.current; brushRef.current = null; brushScreenRef.current = null;
      if (item.points.length > 1) commit(item); else setDraft(null); return;
    }
    const gesture = gestureRef.current; if (!gesture) return;
    const point = eventPoint(event) || gesture.start, moved = Math.hypot(event.clientX - gesture.startX, event.clientY - gesture.startY) >= 3;
    gestureRef.current = null;
    if (gesture.kind === "two") { if (moved) commit({ type: gesture.tool, points: [gesture.start, point], ...drawingDefaults(gesture.tool, defaultColor, gesture.start, barStep) }); else setDraft(null); }
  };

  const startMove = (event, item, kind = "whole", index = null) => {
    if (tool !== "cursor" || item.locked) return;
    focusOverlay(); event.preventDefault(); event.stopPropagation(); onSelect?.(item.id);
    if (item.type === "brush") return; // Freehand is deliberately not editable/resizable.
    const market = rawMarketPoint(event); if (!market) return;
    onChange?.(drawings, { checkpoint: true });
    setDrag({ id: item.id, kind, index, originMarket: market, originPoints: item.points.map((p) => ({ ...p })) });
    try { event.currentTarget.setPointerCapture?.(event.pointerId); } catch { /* ignored */ }
  };
  const copySelected = () => {
    const item = drawings.find((x) => x.id === selectedId); if (!item) return;
    try { localStorage.setItem(DRAWING_CLIPBOARD, JSON.stringify(item)); } catch { /* ignored */ }
  };
  const pasteDrawing = () => {
    let copied = null; try { copied = JSON.parse(localStorage.getItem(DRAWING_CLIPBOARD) || "null"); } catch { copied = null; }
    if (!copied?.type || !Array.isArray(copied.points)) return;
    const basePrice = Number(copied.points[0]?.price || 0), dt = Math.max(1, barStep * 2), dp = Math.abs(basePrice) * 0.002 || 0.1;
    const points = copied.points.map((point) => ({ ...point, time: Number(point.time) + (copied.type === "horizontal" ? 0 : dt), price: Number(point.price) + (copied.type === "vertical" ? 0 : dp) }));
    const item = { ...copied, id: drawingId(copied.type), points, locked: false, ...drawingMeta };
    const next = [...drawings, item]; onChange?.(next); onSelect?.(item.id); onToolChange?.("cursor");
  };
  const handleKeyDown = (event) => {
    const modifier = event.ctrlKey || event.metaKey, key = String(event.key || "").toLowerCase();
    if (modifier && key === "z") { event.preventDefault(); if (event.shiftKey) onRedo?.(); else onUndo?.(); return; }
    if (modifier && key === "y") { event.preventDefault(); onRedo?.(); return; }
    if (modifier && key === "c") { event.preventDefault(); copySelected(); return; }
    if (modifier && key === "v") { event.preventDefault(); pasteDrawing(); return; }
    if ((event.key === "Delete" || event.key === "Backspace") && selectedId) { event.preventDefault(); onDeleteSelected?.(selectedId); }
  };

  const display = [...drawings.filter((x) => x.visible !== false), ...(draft ? [{ ...draft, id: "__draft__", visible: true }] : [])];
  const selectable = tool === "cursor";
  return <svg ref={svgRef} tabIndex={0} aria-label="Chart drawing layer" className="chart-drawing-overlay" width={dimensions.width} height={dimensions.height}
    style={{ pointerEvents: "none", outline: "none" }} onPointerMove={handlePointerMove} onPointerUp={handlePointerUp} onPointerCancel={handlePointerUp} onKeyDown={handleKeyDown}>
    <defs><marker id="ledger-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="context-stroke" /></marker></defs>
    {tool !== "cursor" && <rect x="0" y="0" width={dimensions.width} height={dimensions.height} fill="transparent" style={{ pointerEvents: "all", cursor: tool === "brush" ? "crosshair" : "crosshair" }} onPointerDown={handlePointerDown} />}
    {display.map((item) => <Drawing key={item.id} item={item} toScreen={toScreen} width={dimensions.width} height={dimensions.height} selected={selectedId === item.id} selectable={selectable}
      onMove={(e) => startMove(e, item)} onPointMove={(e, index) => startMove(e, item, "point", index)} />)}
  </svg>;
}

function Drawing({ item, toScreen, width, height, selected, selectable, onMove, onPointMove }) {
  const points = (item.points || []).map(toScreen), color = lineColor(item), strokeWidth = Number(item.lineWidth || 2), strokeDasharray = dash(item);
  const common = { stroke: color, strokeWidth, strokeDasharray, opacity: Number(item.opacity ?? 1), fill: "none", vectorEffect: "non-scaling-stroke", style: { pointerEvents: selectable ? "stroke" : "none", cursor: selectable ? "pointer" : "default" }, onPointerDown: onMove };
  const allowHandles = selected && selectable && item.type !== "brush" && !item.locked;
  const handles = allowHandles ? points.map((p, index) => p && <circle key={index} cx={p.x} cy={p.y} r="5" fill="#fff" stroke={color} strokeWidth="2" style={{ pointerEvents: "all", cursor: "grab" }} onPointerDown={(e) => onPointMove(e, index)} />) : null;

  if (item.type === "horizontal" || item.type === "horizontal-ray") {
    const p = points[0]; if (!p) return null; const x1 = item.type === "horizontal-ray" ? clamp(p.x, 0, width) : 0, label = Number(item.points[0]?.price);
    return <g><line x1={x1} y1={p.y} x2={width} y2={p.y} {...common}/><PriceTag x={width} y={p.y} price={label} color={color}/>{handles}</g>;
  }
  if (item.type === "vertical") { const p = points[0]; if (!p) return null; return <g><line x1={p.x} y1="0" x2={p.x} y2={height} {...common}/>{handles}</g>; }
  if (item.type === "trend" || item.type === "arrow") {
    const [a,b]=points; if(!a||!b)return draftHint(item, points, color);
    return <g><line x1={a.x} y1={a.y} x2={b.x} y2={b.y} {...common} markerEnd={item.type === "arrow" ? "url(#ledger-arrow)" : undefined}/>{handles}</g>;
  }
  if (item.type === "rectangle") {
    const [a,b]=points; if(!a||!b)return draftHint(item, points, color);
    const ax=clamp(a.x,0,width), bx=clamp(b.x,0,width), rawX=Math.min(ax,bx), y=Math.min(a.y,b.y), rawW=Math.abs(bx-ax), h=Math.abs(b.y-a.y);
    // A rectangle drawn on 1m can span only a fraction of one 1h candle. Keep
    // the true timestamp anchors, but enforce a tiny render-only minimum width
    // so the object remains visible/selectable instead of appearing to vanish.
    const hasTimeSpan = Number(item.points?.[0]?.time) !== Number(item.points?.[1]?.time);
    const w = hasTimeSpan && rawW > 0 && rawW < 2 ? 2 : rawW;
    const x = Math.min(Math.max(0, rawX - Math.max(0, w - rawW) / 2), Math.max(0, width - w));
    return <g><rect x={x} y={y} width={w} height={h} stroke={color} strokeWidth={strokeWidth} strokeDasharray={strokeDasharray} fill={rgba(item.fillColor || color, Number(item.fillOpacity ?? .12))} opacity={Number(item.opacity ?? 1)} vectorEffect="non-scaling-stroke" style={{pointerEvents:selectable?"all":"none",cursor:selectable?"pointer":"default"}} onPointerDown={onMove}/>{handles}</g>;
  }
  if (item.type === "brush") {
    const clean=points.filter(Boolean); if(clean.length<2)return draftHint(item, points, color);
    return <g><polyline points={clean.map(p=>`${p.x},${p.y}`).join(" ")} strokeLinecap="round" strokeLinejoin="round" {...common}/></g>;
  }
  if (item.type === "text") {
    const p=points[0]; if(!p)return null; const fontSize=Number(item.fontSize||12), bg=item.backgroundColor||"#111827";
    return <g style={{pointerEvents:selectable?"all":"none",cursor:selectable?"pointer":"default"}} onPointerDown={onMove}><rect x={p.x-4} y={p.y-fontSize-7} width={Math.max(46,(item.text||"").length*(fontSize*.6)+8)} height={fontSize+10} rx="4" fill={rgba(bg,Number(item.backgroundOpacity??.82))}/><text x={p.x} y={p.y-4} fill={color} fontSize={fontSize} fontWeight="600">{item.text}</text>{handles}</g>;
  }
  if (item.type === "fib") {
    const [a,b]=points; if(!a||!b)return draftHint(item, points, color);
    const priceA=Number(item.points[0].price), priceB=Number(item.points[1].price), ax=clamp(a.x,0,width), bx=clamp(b.x,0,width);
    let x1=Math.min(ax,bx), x2=Math.max(ax,bx);
    if (Number(item.points?.[0]?.time) !== Number(item.points?.[1]?.time) && x2 - x1 > 0 && x2 - x1 < 2) {
      const mid=(x1+x2)/2; x1=Math.max(0,mid-1); x2=Math.min(width,mid+1);
    }
    const levels=(item.fibLevels||DEFAULT_FIB_LEVELS).filter((level)=>level.visible!==false);
    return <g onPointerDown={onMove} style={{pointerEvents:selectable?"all":"none",cursor:selectable?"pointer":"default"}}>
      {Number(item.fibFillOpacity||0)>0 && <rect x={x1} y={Math.min(a.y,b.y)} width={Math.max(1,x2-x1)} height={Math.abs(b.y-a.y)} fill={rgba(item.fibFillColor||color,Number(item.fibFillOpacity||0))}/>} 
      {levels.map(level=>{const value=Number(level.value), price=priceA+(priceB-priceA)*value, y=a.y+(b.y-a.y)*value, levelColor=level.color||color; return <g key={`${value}-${levelColor}`}><line x1={x1} y1={y} x2={x2} y2={y} stroke={levelColor} strokeWidth={Number(level.lineWidth||1)} strokeDasharray={dash(level)} opacity={value===0||value===1?1:.85}/><text x={Math.min(width-82,x2+5)} y={y+4} fill={levelColor} fontSize="10">{value}{item.showFibPrices===false?"":` · ${price.toFixed(2)}`}</text></g>})}{handles}
    </g>;
  }
  if (POSITION.has(item.type)) {
    const entry=points[0], stop=points[1], target=points[2], end=points[3]; if(!entry||!stop||!target)return null;
    const startX=clamp(entry.x,0,width);
    // Position tools are intentionally right-extending. Old malformed saved width
    // anchors (or an accidental drag to the left) are repaired visually instead of
    // painting a giant box all the way to the left edge of the chart.
    const candidateEnd = Number(end?.x);
    const endX = Number.isFinite(candidateEnd) && candidateEnd > startX + 12 ? clamp(candidateEnd, 0, width) : clamp(startX + 140, 0, width);
    const x1=startX, x2=Math.max(startX+24,endX), boxWidth=Math.max(24,x2-x1);
    const entryPrice=Number(item.points[0].price), stopPrice=Number(item.points[1].price), targetPrice=Number(item.points[2].price), risk=Math.abs(entryPrice-stopPrice), rr=risk?Math.abs(targetPrice-entryPrice)/risk:null;
    const profitColor=item.profitColor||"#22c55e", lossColor=item.lossColor||"#ef4444", opacity=Number(item.fillOpacity??.16);
    return <g onPointerDown={onMove} style={{pointerEvents:selectable?"all":"none",cursor:selectable?"pointer":"default"}}>
      <rect x={x1} y={Math.min(entry.y,target.y)} width={boxWidth} height={Math.abs(target.y-entry.y)} fill={rgba(profitColor,opacity)}/>
      <rect x={x1} y={Math.min(entry.y,stop.y)} width={boxWidth} height={Math.abs(stop.y-entry.y)} fill={rgba(lossColor,opacity)}/>
      <line x1={x1} y1={entry.y} x2={x1+boxWidth} y2={entry.y} stroke={item.entryColor||"#e5e7eb"} strokeWidth="1.5"/>
      <line x1={x1} y1={stop.y} x2={x1+boxWidth} y2={stop.y} stroke={lossColor} strokeWidth="1.5"/><line x1={x1} y1={target.y} x2={x1+boxWidth} y2={target.y} stroke={profitColor} strokeWidth="1.5"/>
      <text x={x1+6} y={entry.y-6} fill={item.entryColor||"#e5e7eb"} fontSize="10">{item.type === "long-position" ? "LONG" : "SHORT"} · R:R {rr?rr.toFixed(2):"—"}</text>{handles}
    </g>;
  }
  return null;
}
function PriceTag({ x, y, price, color }) {
  if (!Number.isFinite(price)) return null; const text=price.toFixed(Math.abs(price)>=1000?2:4), w=Math.max(54,text.length*7+10), left=Math.max(0,x-w);
  return <g style={{pointerEvents:"none"}}><rect x={left} y={y-9} width={w} height="18" rx="3" fill={color}/><text x={left+5} y={y+4} fill="#fff" fontSize="10" fontWeight="700">{text}</text></g>;
}
function draftHint(item, points, color, text = "Drag to size") {
  if (item.id !== "__draft__") return null; const p = points.find(Boolean); if (!p) return null;
  return <g><circle cx={p.x} cy={p.y} r="4.5" fill={color}/><text x={p.x+7} y={p.y-7} fill={color} fontSize="10">{text}</text></g>;
}
