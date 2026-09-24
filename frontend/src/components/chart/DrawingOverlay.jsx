import {drawingStyle} from "./drawings/defaults.js";
import { useEffect, useMemo, useRef, useState } from "react";
import {useDrawingViewport} from "./drawings/useDrawingViewport.js";
import {nearestOHLC,translatePointsLogical,constrainPoint,marketTimeToLogical,logicalToMarketTime,logicalToCoordinateInterpolated} from "./drawings/geometry.js";
import { drawingId } from "./drawingStore";

import Drawing from "./drawings/Drawing.jsx";
import {DEFAULT_FIB_LEVELS,TWO_POINT,POSITION} from "./drawings/models.js";
export {DEFAULT_FIB_LEVELS} from "./drawings/models.js";
const DRAWING_CLIPBOARD = "ledger.drawingClipboard.v1";

function numTime(value) {
  if (value == null) return null;
  if (typeof value === "number") return value;
  if (typeof value === "object" && value.year) return Math.floor(Date.UTC(value.year, value.month - 1, value.day) / 1000);
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
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
  const renderToken = useDrawingViewport(chart,series,container);
  const snapBars=useMemo(()=>[...new Map(bars.map(b=>[Date.parse(b.timestamp),b])).entries()].filter(([t])=>Number.isFinite(t)).sort((a,b)=>a[0]-b[0]).map(([,b])=>b),[bars]);
  const [drag, setDrag] = useState(null);
  const svgRef = useRef(null); const brushRef = useRef(null); const gestureRef = useRef(null); const brushScreenRef = useRef(null);
  const barTimes = useMemo(() => cleanBarTimes(bars), [bars]);
  const barStep = useMemo(() => medianStep(barTimes), [barTimes]);

  useEffect(() => { setDraft(null); setDrag(null); gestureRef.current = null; brushRef.current = null; brushScreenRef.current = null; }, [tool]);
  useEffect(()=>{
    const clear=event=>{if(tool==="cursor"&&!svgRef.current?.contains(event.target))onSelect?.(null);};
    container?.addEventListener("pointerdown",clear);
    return()=>container?.removeEventListener("pointerdown",clear);
  },[container,tool,onSelect]);
  const dimensions = useMemo(() => ({ width: container?.clientWidth || 0, height: container?.clientHeight || 0 }), [container, renderToken]);

  const logicalForTime = (time) => marketTimeToLogical(barTimes, Number(time), barStep);
  const timeForLogical = (logical) => logicalToMarketTime(barTimes, logical, barStep, { clamp: clampToBars });
  const toScreen = (point) => {
    if (!chart || !series || !point) return null;
    const timeScale = chart.timeScale();
    const marketTime = Number(point.time);
    // Exact current-timeframe anchors should use the library's native mapping.
    // Off-grid anchors (for example 10:17 drawn on 1m but viewed on 15m) have
    // no native time coordinate, so interpolate between the surrounding *integer*
    // logical bar coordinates. Passing a fractional logical directly to
    // logicalToCoordinate resolves to the left edge in Lightweight Charts 5.x.
    let x = timeScale.timeToCoordinate(marketTime);
    if (x == null) {
      const logical = logicalForTime(marketTime);
      x = logicalToCoordinateInterpolated(logical, (index) => timeScale.logicalToCoordinate(index));
    }
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
  const eventPoint = (event) => {
    const raw=rawMarketPoint(event);if(!raw||!container)return raw;
    const rect=container.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top;
    let point=nearestOHLC({point:raw,logical:chart.timeScale().coordinateToLogical(x),bars:snapBars,toX:i=>chart.timeScale().logicalToCoordinate(i),toY:p=>series.priceToCoordinate(p),x,y,mode:magnet});
    if(event.shiftKey&&gestureRef.current?.start)point=constrainPoint(gestureRef.current.start,point,toScreen,(sx,sy)=>({time:timeForLogical(chart.timeScale().coordinateToLogical(sx)),price:Number(series.coordinateToPrice(sy))}));
    return point;
  };

  const commit = (item) => {
    if (!item) return;
    const defaults = drawingDefaults(item.type, item.color || defaultColor, item.points?.[0], barStep);
    const nextItem = { ...defaults, ...item, ...drawingStyle(item.type), id: item.id || drawingId(item.type), visible: true, locked: false, ...drawingMeta };
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
      const item = drawings.find((x) => x.id === drag.id); if (!item || item.locked) return;
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
        const logical = chart.timeScale().coordinateToLogical(event.clientX - container.getBoundingClientRect().left);
        const deltaLogical = Number(logical) - Number(drag.originLogical);
        const priceDelta = Number(point.price) - Number(drag.originMarket.price);
        updated = { ...item, points: translatePointsLogical(drag.originPoints, drag.originLogicals, deltaLogical, priceDelta, timeForLogical) };
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
    if (tool !== "cursor") return;
    focusOverlay(); event.preventDefault(); event.stopPropagation(); onSelect?.(item.id);
    if(item.locked)return;
    const market = rawMarketPoint(event); if (!market) return;
    const rect = container.getBoundingClientRect();
    const originLogical = chart.timeScale().coordinateToLogical(event.clientX - rect.left);
    if (!Number.isFinite(Number(originLogical))) return;
    onChange?.(drawings, { checkpoint: true });
    setDrag({ id: item.id, kind, index, originMarket: market, originLogical: Number(originLogical), originLogicals: item.points.map((p) => logicalForTime(Number(p.time))), originPoints: item.points.map((p) => ({ ...p })) });
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
    if(event.key==="Escape"){event.preventDefault();setDraft(null);setDrag(null);gestureRef.current=null;brushRef.current=null;onSelect?.(null);onToolChange?.("cursor");return;}
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
