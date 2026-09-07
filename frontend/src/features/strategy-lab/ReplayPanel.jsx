import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import SymbolSearch from "../../components/SymbolSearch";
import { TIMEZONE_OPTIONS, resolvedZone } from "../../utils/timezones";
import ReplayChart from "./ReplayChart";
import WatchlistBar from "../../components/WatchlistBar";
import ChartDrawingToolbar from "../../components/chart/ChartDrawingToolbar";
import DrawingObjectPanel from "../../components/chart/DrawingObjectPanel";
import { loadDrawings, saveDrawings } from "../../components/chart/drawingStore";

const TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h"];
const INDICATOR_COLORS = ["#60a5fa", "#f59e0b", "#a78bfa", "#22c55e", "#f43f5e", "#06b6d4", "#e879f9", "#84cc16", "#fb7185", "#38bdf8", "#facc15", "#c084fc"];
let indicatorSequence = 0;

function daysAgo(days) { const d = new Date(); d.setDate(d.getDate() - days); return d.toISOString().slice(0, 10); }
function addDays(value, days) { const d = new Date(`${value}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + days); return d.toISOString().slice(0, 10); }
function money(value) { return value == null || !Number.isFinite(Number(value)) ? "—" : `$${Number(value).toFixed(2)}`; }
function fmt(value, zone) { return value ? new Intl.DateTimeFormat("en-GB", { timeZone: resolvedZone(zone), dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—"; }
function nyDate(value) { return value ? new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value)) : ""; }
function currentValue(indicator, lastTimestamp) {
  const eligible = (indicator?.values || []).filter((point) => new Date(point.timestamp).getTime() <= new Date(lastTimestamp).getTime());
  return eligible.length ? Number(eligible[eligible.length - 1].value) : null;
}
function countThroughTimestamp(bars, timestamp, fallback = 1) {
  if (!timestamp || !Array.isArray(bars) || !bars.length) return Math.min(Math.max(1, Number(fallback || 1)), bars?.length || 1);
  const cutoff = new Date(timestamp).getTime();
  const count = bars.reduce((total, bar) => total + (new Date(bar.timestamp).getTime() <= cutoff ? 1 : 0), 0);
  return Math.min(Math.max(1, count || Number(fallback || 1)), bars.length);
}
function indicatorRequestSignature(item, dataset, symbol, timeframe, session, replayDate, replayEndDate, startTime, context) {
  return JSON.stringify({
    id: item.id, key: item.key, params: item.params || {},
    symbol, timeframe, session, replayDate, replayEndDate, startTime,
    contextBars: context.contextBars, contextDays: context.contextDays,
    datasetCount: dataset?.count, sourceTimeframe: dataset?.source_timeframe, aggregation: dataset?.aggregation,
  });
}
function contextArgs(mode, customBars) {
  if (mode === "1d") return { contextDays: 1, contextBars: 0 };
  if (mode === "5d") return { contextDays: 8, contextBars: 0 };
  if (mode === "1m") return { contextDays: 31, contextBars: 0 };
  if (mode === "3m") return { contextDays: 93, contextBars: 0 };
  return { contextDays: null, contextBars: Math.max(0, Number(customBars || 0)) };
}
function makeIndicator(spec, colorIndex) {
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
function plannedMetrics(position) {
  if (!position) return { risk: null, rr: null };
  const entry = Number(position.entry_price); const qty = Number(position.quantity || 0);
  const stop = position.stop_loss == null ? null : Number(position.stop_loss);
  const target = position.take_profit == null ? null : Number(position.take_profit);
  const perShareRisk = stop == null ? null : Math.abs(entry - stop);
  return {
    risk: perShareRisk == null ? null : perShareRisk * qty,
    rr: perShareRisk && target != null ? Math.abs(target - entry) / perShareRisk : null,
  };
}

export default function ReplayPanel({ indicators = [], onError }) {
  const initialDate = daysAgo(30);
  const [symbol, setSymbol] = useState("AAPL");
  const [symbolInput, setSymbolInput] = useState("AAPL");
  const [replayDate, setReplayDate] = useState(initialDate);
  const [replayEndDate, setReplayEndDate] = useState(addDays(initialDate, 7));
  const [startTime, setStartTime] = useState("09:30");
  const [timeframe, setTimeframe] = useState(() => localStorage.getItem("ledger.chartTimeframe") || "5m");
  const [session, setSession] = useState("regular");
  const [contextMode, setContextMode] = useState("5d");
  const [contextBars, setContextBars] = useState(500);
  const [timeZone, setTimeZone] = useState("America/New_York");
  const [dataset, setDataset] = useState(null);
  const [visibleCount, setVisibleCount] = useState(0);
  const [furthestVisibleCount, setFurthestVisibleCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [expanded, setExpanded] = useState(false);
  const [followReplay, setFollowReplay] = useState(false);
  const [jumpToken, setJumpToken] = useState(0);
  const [integrityCompromised, setIntegrityCompromised] = useState(false);
  const [selectedIndicators, setSelectedIndicators] = useState([]);
  const [indicatorDefaultsInitialised, setIndicatorDefaultsInitialised] = useState(false);
  const [indicatorData, setIndicatorData] = useState({});
  const [editingIndicatorId, setEditingIndicatorId] = useState(null);
  const [positionAmount, setPositionAmount] = useState("1000");
  const [orderType, setOrderType] = useState("market");
  const [entryPrice, setEntryPrice] = useState("");
  const [stop, setStop] = useState("");
  const [target, setTarget] = useState("");
  const [setup, setSetup] = useState("");
  const [pendingOrder, setPendingOrder] = useState(null);
  const [pendingClose, setPendingClose] = useState(false);
  const [position, setPosition] = useState(null);
  const [closedTrade, setClosedTrade] = useState(null);
  const [journalStatus, setJournalStatus] = useState("");
  const [checkpointStatus, setCheckpointStatus] = useState("");
  const [drawingTool, setDrawingTool] = useState("cursor");
  const [drawingMagnet, setDrawingMagnet] = useState(() => localStorage.getItem("ledger.drawingMagnet") || "weak");
  const [drawings, setDrawings] = useState([]);
  const [selectedDrawingId, setSelectedDrawingId] = useState(null);
  const [objectsOpen, setObjectsOpen] = useState(false);
  const [drawingHistory, setDrawingHistory] = useState([]);
  const [drawingRedo, setDrawingRedo] = useState([]);

  useEffect(() => {
    if (!indicators.length || indicatorDefaultsInitialised) return;
    const defaults = ["volume", "ema", "vwap"].map((key) => indicators.find((item) => item.key === key)).filter(Boolean).map((spec, index) => makeIndicator(spec, index));
    setSelectedIndicators(defaults);
    setIndicatorDefaultsInitialised(true);
  }, [indicators, indicatorDefaultsInitialised]);

  const bars = dataset?.bars || [];
  const visibleBars = bars.slice(0, visibleCount);
  const currentBar = visibleBars[visibleBars.length - 1];
  const nextBar = bars[visibleCount];
  const finished = Boolean(dataset && visibleCount >= bars.length);
  const atFrontier = visibleCount >= furthestVisibleCount;
  const context = contextArgs(contextMode, contextBars);
  const drawingScope = `replay:${symbol}:${replayDate}:${startTime}`;

  useEffect(() => {
    setDrawings(loadDrawings(drawingScope, symbol));
    setDrawingHistory([]); setDrawingRedo([]); setSelectedDrawingId(null);
  }, [drawingScope, symbol]);
  useEffect(() => { saveDrawings(drawingScope, symbol, drawings); }, [drawingScope, symbol, drawings]);

  const applyDrawings = (next, meta = {}) => { if (meta.checkpoint) { setDrawingHistory((h) => [...h.slice(-49), drawings]); setDrawingRedo([]); return; } if (meta.transient) { setDrawings(next); return; } setDrawingHistory((h) => [...h.slice(-49), drawings]); setDrawingRedo([]); setDrawings(next); };
  const undoDrawing = () => { if (!drawingHistory.length) return; const prev = drawingHistory[drawingHistory.length - 1]; setDrawingRedo((r) => [drawings, ...r]); setDrawingHistory((h) => h.slice(0, -1)); setDrawings(prev); };
  const redoDrawing = () => { if (!drawingRedo.length) return; const next = drawingRedo[0]; setDrawingHistory((h) => [...h, drawings]); setDrawingRedo((r) => r.slice(1)); setDrawings(next); };
  const deleteDrawing = (id) => { if (!id) return; applyDrawings(drawings.filter((x) => x.id !== id)); if (selectedDrawingId === id) setSelectedDrawingId(null); };
  const toggleDrawing = (id, key) => applyDrawings(drawings.map((x) => x.id === id ? { ...x, [key]: !x[key] } : x));
  const patchDrawing = (id, patch) => applyDrawings(drawings.map((x) => x.id === id ? { ...x, ...patch } : x));
  const usePositionDrawing = (drawing) => {
    const [entry, stopPoint, targetPoint] = drawing?.points || [];
    if (!entry || !stopPoint || !targetPoint) return;
    setOrderType("limit"); setEntryPrice(Number(entry.price).toFixed(4)); setStop(Number(stopPoint.price).toFixed(4)); setTarget(Number(targetPoint.price).toFixed(4));
    setCheckpointStatus(`${drawing.type === "long-position" ? "Long" : "Short"} position drawing copied into the Replay order ticket. Review the values, then place the order.`);
  };

  const fetchReplay = async (config, restore = null) => {
    const activeSymbol = String(config.symbol || symbol).trim().toUpperCase();
    if (!activeSymbol) return;
    setLoading(true); setPlaying(false); onError?.(""); setJournalStatus("");
    try {
      const response = await api.strategyLabReplayBars(
        activeSymbol, config.replayDate, config.replayEndDate, config.startTime,
        config.timeframe, config.session, config.contextBars, config.contextDays,
      );
      setSymbol(activeSymbol); setSymbolInput(activeSymbol); setTimeframe(config.timeframe); setSession(config.session); setDataset(response);
      const initial = response.initial_visible_count || 1;
      const restoredVisible = restore?.anchorTimestamp
        ? countThroughTimestamp(response.bars, restore.anchorTimestamp, initial)
        : restore ? Math.min(Number(restore.visibleCount || initial), response.bars.length) : initial;
      const frontierCount = restore?.frontierTimestamp
        ? countThroughTimestamp(response.bars, restore.frontierTimestamp, restoredVisible)
        : restore ? Number(restore.furthestVisibleCount || restoredVisible) : initial;
      const restoredFurthest = Math.min(Math.max(restoredVisible, frontierCount), response.bars.length);
      setVisibleCount(restoredVisible); setFurthestVisibleCount(restoredFurthest);
      setPosition(restore?.position || null); setClosedTrade(null); setPendingOrder(restore?.pendingOrder || null); setPendingClose(false);
      setIntegrityCompromised(Boolean(restore?.integrityCompromised));
      setFollowReplay(restore?.followReplay ?? false);
      if (!restore?.preserveViewport) setJumpToken((value) => value + 1);
    } catch (error) { onError?.(error.message || String(error)); }
    finally { setLoading(false); }
  };

  const load = async () => {
    const typed = String(symbolInput || symbol).trim().toUpperCase();
    await fetchReplay({ symbol: typed, replayDate, replayEndDate, startTime, timeframe, session, ...context });
  };

  const switchTimeframe = async (nextTimeframe) => {
    if (!nextTimeframe || nextTimeframe === timeframe) return;
    const anchorTimestamp = currentBar?.timestamp || null;
    const frontierTimestamp = bars[Math.max(0, furthestVisibleCount - 1)]?.timestamp || anchorTimestamp;
    if (!dataset) { setTimeframe(nextTimeframe); return; }
    await fetchReplay(
      { symbol, replayDate, replayEndDate, startTime, timeframe: nextTimeframe, session, ...context },
      {
        visibleCount, furthestVisibleCount, anchorTimestamp, frontierTimestamp,
        position, pendingOrder, integrityCompromised, followReplay, preserveViewport: true,
      },
    );
  };

  useEffect(() => {
    if (!dataset || !selectedIndicators.length) return;
    let cancelled = false;
    const pending = selectedIndicators.map((item) => {
      const signature = indicatorRequestSignature(item, dataset, symbol, timeframe, session, replayDate, replayEndDate, startTime, context);
      if (indicatorData[item.id]?._signature === signature) return null;
      return { item, signature };
    }).filter(Boolean);
    if (!pending.length) return undefined;
    Promise.all(pending.map(async ({ item, signature }) => {
      try {
        const data = await api.strategyLabReplayIndicator(
          symbol, replayDate, replayEndDate, startTime, item.key, timeframe, session,
          context.contextBars, context.contextDays, item.params,
        );
        return [item.id, { ...data, label: indicatorLabel(item, indicators, symbol), _signature: signature }];
      } catch { return null; }
    })).then((items) => {
      if (cancelled) return;
      const updates = Object.fromEntries(items.filter(Boolean));
      setIndicatorData((old) => ({ ...old, ...updates }));
    });
    return () => { cancelled = true; };
  }, [dataset, selectedIndicators, symbol, replayDate, replayEndDate, startTime, timeframe, session, context.contextBars, context.contextDays, indicators, indicatorData]);


  useEffect(() => {
    if (!playing || !dataset || finished) return undefined;
    const interval = Math.max(80, Math.round(1000 / Number(playbackSpeed || 1)));
    const timer = globalThis.setInterval(() => advance(1), interval);
    return () => globalThis.clearInterval(timer);
  });
  useEffect(() => { if (finished) setPlaying(false); }, [finished]);

  useEffect(() => {
    const handler = (event) => {
      if (!dataset || ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return;
      if (event.code === "Space") { event.preventDefault(); setPlaying((value) => !value); }
      if (event.key === "ArrowRight") { event.preventDefault(); advance(event.shiftKey ? 5 : 1); }
      if (event.key === "ArrowLeft") { event.preventDefault(); rewindOne(); }
      if (event.key === "Escape" && expanded) setExpanded(false);
    };
    globalThis.addEventListener("keydown", handler);
    return () => globalThis.removeEventListener("keydown", handler);
  });

  const closeTrade = async (exitPriceValue, exitTime, reason, pos = position) => {
    if (!pos) return;
    const mult = pos.direction === "long" ? 1 : -1;
    const gross = (Number(exitPriceValue) - pos.entry_price) * mult * pos.quantity;
    const trade = { ...pos, exit_price: Number(exitPriceValue), exit_time: exitTime, exit_reason: reason, net_pnl: gross };
    setClosedTrade(trade); setPosition(null); setPendingClose(false);
    try {
      const saved = await api.createJournalTrade({
        source: "replay", name: `Replay · ${symbol}`, account: "Replay", ticker: symbol,
        direction: trade.direction, opened_at: trade.entry_time, closed_at: trade.exit_time,
        entry_price: trade.entry_price, exit_price: trade.exit_price, quantity: trade.quantity,
        position_amount: Number(trade.position_amount || positionAmount || 0) || null, position_currency: "USD",
        stop_loss: trade.stop_loss, take_profit: trade.take_profit, fees: 0,
        trade_type: "replay", setup: trade.setup || setup, entry_timeframe: timeframe,
        notes: `Replay exit: ${reason}. Integrity: ${integrityCompromised ? "review/rewound" : "clean"}. MFE/share: ${Number(trade.mfe_per_share || 0).toFixed(4)}. MAE/share: ${Number(trade.mae_per_share || 0).toFixed(4)}.`,
      });
      setJournalStatus(`Saved to Journal as replay trade #${saved.id}. Add reasoning/screenshots there when you review it.`);
    } catch (error) { setJournalStatus(`Trade closed, but Journal save failed: ${error.message}`); }
  };

  const evaluateBar = async (bar, pos) => {
    if (!pos) return { closed: false, position: pos };
    const o = Number(bar.open), h = Number(bar.high), l = Number(bar.low);
    const favourable = pos.direction === "long" ? h - pos.entry_price : pos.entry_price - l;
    const adverse = pos.direction === "long" ? pos.entry_price - l : h - pos.entry_price;
    const updated = { ...pos, mfe_per_share: Math.max(Number(pos.mfe_per_share || 0), favourable), mae_per_share: Math.max(Number(pos.mae_per_share || 0), adverse) };
    setPosition(updated);
    const stopPrice = updated.stop_loss == null ? null : Number(updated.stop_loss);
    const targetPrice = updated.take_profit == null ? null : Number(updated.take_profit);
    if (updated.direction === "long") {
      if (stopPrice != null && o <= stopPrice) { await closeTrade(o, bar.timestamp, "stop_gap", updated); return { closed: true, position: null }; }
      if (targetPrice != null && o >= targetPrice) { await closeTrade(o, bar.timestamp, "target_gap", updated); return { closed: true, position: null }; }
      const stopHit = stopPrice != null && l <= stopPrice; const targetHit = targetPrice != null && h >= targetPrice;
      if (stopHit && targetHit) { await closeTrade(stopPrice, bar.timestamp, "stop_same_bar_conservative", updated); return { closed: true, position: null }; }
      if (stopHit) { await closeTrade(stopPrice, bar.timestamp, "stop", updated); return { closed: true, position: null }; }
      if (targetHit) { await closeTrade(targetPrice, bar.timestamp, "target", updated); return { closed: true, position: null }; }
    } else {
      if (stopPrice != null && o >= stopPrice) { await closeTrade(o, bar.timestamp, "stop_gap", updated); return { closed: true, position: null }; }
      if (targetPrice != null && o <= targetPrice) { await closeTrade(o, bar.timestamp, "target_gap", updated); return { closed: true, position: null }; }
      const stopHit = stopPrice != null && h >= stopPrice; const targetHit = targetPrice != null && l <= targetPrice;
      if (stopHit && targetHit) { await closeTrade(stopPrice, bar.timestamp, "stop_same_bar_conservative", updated); return { closed: true, position: null }; }
      if (stopHit) { await closeTrade(stopPrice, bar.timestamp, "stop", updated); return { closed: true, position: null }; }
      if (targetHit) { await closeTrade(targetPrice, bar.timestamp, "target", updated); return { closed: true, position: null }; }
    }
    return { closed: false, position: updated };
  };

  const advance = async (count = 1) => {
    if (!dataset || count <= 0) return;
    let cursor = visibleCount;
    let remaining = count;
    if (cursor < furthestVisibleCount) {
      const known = Math.min(remaining, furthestVisibleCount - cursor);
      cursor += known; remaining -= known;
      setVisibleCount(cursor);
      if (!remaining) return;
    }
    let active = position;
    let order = pendingOrder;
    let closeQueued = pendingClose;
    for (let i = 0; i < remaining && cursor < bars.length; i += 1) {
      const bar = bars[cursor];
      if (order && !active) {
        const fill = orderFill(bar, order);
        if (fill != null) {
          const amount = Number(order.position_amount || 0); const quantity = amount > 0 ? amount / fill : 1;
          const candidate = {
            direction: order.direction, entry_price: fill, entry_time: bar.timestamp, quantity,
            stop_loss: order.stop_loss, take_profit: order.take_profit, order_type: order.order_type,
            position_amount: amount || null, setup: order.setup || "", mfe_per_share: 0, mae_per_share: 0,
          };
          if (!validProtection(candidate)) {
            onError?.("Stop/target are on the wrong side of the filled entry for the selected direction.");
            setPendingOrder(null); setPlaying(false); return;
          }
          active = candidate; order = null; setPosition(candidate); setClosedTrade(null); setPendingOrder(null); setJournalStatus("");
        }
      }
      if (closeQueued && active) {
        await closeTrade(Number(bar.open), bar.timestamp, "manual_next_bar_open", active);
        active = null; closeQueued = false; setPendingClose(false);
      }
      if (active) {
        const evaluated = await evaluateBar(bar, active);
        active = evaluated.position;
      }
      cursor += 1;
    }
    setVisibleCount(cursor); setFurthestVisibleCount((old) => Math.max(old, cursor));
  };

  const rewindOne = () => {
    if (!dataset || visibleCount <= (dataset.initial_visible_count || 1)) return;
    if (position || pendingOrder || pendingClose) { onError?.("Close/cancel the active replay trade or order before rewinding."); return; }
    setPlaying(false); setVisibleCount((value) => Math.max(dataset.initial_visible_count || 1, value - 1)); setIntegrityCompromised(true); setFollowReplay(false);
  };

  const jumpNextSession = async () => {
    if (!currentBar) return;
    const currentDate = nyDate(currentBar.timestamp);
    const nextIndex = bars.findIndex((bar, index) => index >= visibleCount && nyDate(bar.timestamp) !== currentDate);
    if (nextIndex >= 0) await advance(nextIndex - visibleCount + 1);
  };

  const placeOrder = (direction) => {
    if (!dataset || !nextBar || !atFrontier) { onError?.("Return to the newest revealed candle before placing a replay order."); return; }
    const explicitEntry = orderType === "market" ? null : Number(entryPrice);
    if (orderType !== "market" && (!Number.isFinite(explicitEntry) || explicitEntry <= 0)) { onError?.("Enter a valid order price for limit/stop entry."); return; }
    const amount = Number(positionAmount || 0);
    if (!(amount > 0)) { onError?.("Position value must be greater than zero."); return; }
    setPendingOrder({
      direction, order_type: orderType, entry_price: explicitEntry,
      stop_loss: stop === "" ? null : Number(stop), take_profit: target === "" ? null : Number(target),
      position_amount: amount, setup,
    });
    setClosedTrade(null); setJournalStatus("");
  };

  const addIndicator = (key) => {
    if (!key) return;
    const spec = indicators.find((item) => item.key === key);
    if (!spec) return;
    setSelectedIndicators((old) => [...old, makeIndicator(spec, old.length)]);
  };
  const patchIndicator = (id, patch) => setSelectedIndicators((old) => old.map((item) => item.id === id ? { ...item, ...patch } : item));
  const patchIndicatorParam = (id, key, value) => setSelectedIndicators((old) => old.map((item) => item.id === id ? { ...item, params: { ...item.params, [key]: value } } : item));

  const visibleIndicators = useMemo(() => {
    if (!currentBar) return [];
    const cutoff = new Date(currentBar.timestamp).getTime();
    return selectedIndicators.map((item) => {
      const data = indicatorData[item.id] || {};
      return { ...data, ...item, label: indicatorLabel(item, indicators, symbol), values: (data.values || []).filter((point) => new Date(point.timestamp).getTime() <= cutoff) };
    });
  }, [indicatorData, currentBar, selectedIndicators, indicators]);
  const volumeIndicator = visibleIndicators.find((item) => item.key === "volume");
  const showVolume = Boolean(volumeIndicator && volumeIndicator.visible !== false);
  const volumeStyle = volumeIndicator ? { upColor: volumeIndicator.upColor || "#34d399", downColor: volumeIndicator.downColor || "#f87171", opacity: Number(volumeIndicator.volumeOpacity ?? .28) } : null;
  const paneIndicators = visibleIndicators.filter((item) => item.key !== "volume" && !item.overlay && item.visible !== false);
  const metrics = plannedMetrics(position);

  const saveCheckpoint = () => {
    if (!dataset) return;
    const payload = {
      config: { symbol, replayDate, replayEndDate, startTime, timeframe, session, ...context },
      visibleCount, furthestVisibleCount, integrityCompromised, followReplay,
      selectedIndicators, position, pendingOrder, setup, positionAmount, orderType, entryPrice, stop, target,
    };
    localStorage.setItem("ledger.replay.checkpoint", JSON.stringify(payload)); setCheckpointStatus("Checkpoint saved in this browser.");
  };
  const resumeCheckpoint = async () => {
    const raw = localStorage.getItem("ledger.replay.checkpoint");
    if (!raw) { setCheckpointStatus("No saved Replay checkpoint found in this browser."); return; }
    try {
      const saved = JSON.parse(raw); const cfg = saved.config || {};
      setReplayDate(cfg.replayDate); setReplayEndDate(cfg.replayEndDate); setStartTime(cfg.startTime); setTimeframe(cfg.timeframe); setSession(cfg.session);
      setContextMode(cfg.contextDays === 1 ? "1d" : cfg.contextDays === 8 ? "5d" : cfg.contextDays === 31 ? "1m" : cfg.contextDays === 93 ? "3m" : "custom");
      if (cfg.contextBars != null) setContextBars(cfg.contextBars);
      setSelectedIndicators(saved.selectedIndicators || []); setSetup(saved.setup || ""); setPositionAmount(String(saved.positionAmount || "1000"));
      setOrderType(saved.orderType || "market"); setEntryPrice(saved.entryPrice || ""); setStop(saved.stop || ""); setTarget(saved.target || "");
      await fetchReplay(cfg, saved); setCheckpointStatus("Checkpoint resumed.");
    } catch (error) { setCheckpointStatus(`Could not resume checkpoint: ${error.message}`); }
  };

  const workspace = dataset && <div className={expanded ? "fixed inset-0 z-50 overflow-auto bg-stone-100 p-3" : "mt-4"}>
    <div className={`rounded-xl border border-stone-200 bg-white ${expanded ? "min-h-[calc(100vh-24px)] p-3 shadow-2xl" : "p-4"}`}>
      <div className="flex flex-wrap items-center gap-2 border-b border-stone-100 pb-3">
        <div className="mr-2"><strong>{symbol}</strong> <span className="text-xs text-stone-500">{timeframe} · {dataset?.effective_session||session} · {fmt(currentBar?.timestamp, timeZone)}</span></div>
        {expanded && <div className="replay-fullscreen-timeframes">{TIMEFRAMES.map((tf) => <button key={tf} type="button" onClick={() => switchTimeframe(tf)} className={`chart-toolbar-btn ${timeframe === tf ? "active" : ""}`}>{tf}</button>)}</div>}
        <button disabled={visibleCount <= (dataset.initial_visible_count || 1) || position || pendingOrder} onClick={rewindOne} className="rounded-md border border-stone-300 bg-white px-3 py-2 text-xs">◀ -1</button>
        <button disabled={!nextBar} onClick={() => advance(1)} className="rounded-md border border-stone-300 bg-white px-3 py-2 text-xs">▶ +1</button>
        <button disabled={!nextBar} onClick={() => advance(5)} className="rounded-md border border-stone-300 bg-white px-3 py-2 text-xs">+5</button>
        <button disabled={!nextBar} onClick={() => setPlaying((value) => !value)} className="rounded-md bg-stone-900 px-3 py-2 text-xs font-medium text-white">{playing ? "Pause" : "Play"}</button>
        <select value={playbackSpeed} onChange={(e) => setPlaybackSpeed(Number(e.target.value))} className="rounded-md border border-stone-300 px-2 py-2 text-xs"><option value="0.5">0.5x</option><option value="1">1x</option><option value="2">2x</option><option value="5">5x</option><option value="10">10x</option></select>
        <button onClick={jumpNextSession} disabled={!nextBar} className="rounded-md border border-stone-300 bg-white px-3 py-2 text-xs">Next session</button>
        <button onClick={() => { const next = !followReplay; setFollowReplay(next); if (next) setJumpToken((value) => value + 1); }} className={`rounded-md border px-3 py-2 text-xs ${followReplay ? "border-blue-300 bg-blue-50 text-blue-800" : "border-stone-300 bg-white"}`}>Follow {followReplay ? "on" : "off"}</button>
        <button onClick={() => setJumpToken((value) => value + 1)} className="rounded-md border border-stone-300 bg-white px-3 py-2 text-xs">Current candle</button>
        <button onClick={saveCheckpoint} className="rounded-md border border-stone-300 bg-white px-3 py-2 text-xs">Save replay</button>
        <button onClick={() => fetchReplay({ symbol, replayDate, replayEndDate, startTime, timeframe, session, ...context })} className="rounded-md border border-stone-300 bg-white px-3 py-2 text-xs">Restart clean</button>
        <button onClick={() => setObjectsOpen((value) => !value)} className={`rounded-md border px-3 py-2 text-xs ${objectsOpen ? "active-btn" : "border-stone-300 bg-white"}`}>Objects</button>
        <button onClick={() => setExpanded((value) => !value)} className="ml-auto rounded-md border border-stone-300 bg-white px-3 py-2 text-xs">{expanded ? "Exit full screen" : "Full screen"}</button>
      </div>
      <div className={`mt-3 rounded-md px-3 py-2 text-xs ${integrityCompromised ? "bg-amber-50 text-amber-900" : "bg-emerald-50 text-emerald-900"}`}>
        Replay integrity: <strong>{integrityCompromised ? "review mode · future bars were previously viewed" : "clean"}</strong>. Visible {visibleCount}/{bars.length}. {finished ? "End of loaded replay range." : `Loaded through ${dataset.replay_end_date}.`} <span className="ml-2 text-stone-500">Data: {dataset.provider ? `${dataset.provider} · ` : ""}{dataset.source_timeframe || timeframe}{String(dataset.aggregation||"").includes("aligned_from_1m") ? ` → ${timeframe}` : ""}{dataset.effective_session==="24h" ? " · 24h market" : ""}.</span>
      </div>
      <div className="mt-3 grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0">
          <div className="chart-stage replay-chart-stage">
            <ChartDrawingToolbar tool={drawingTool} onToolChange={setDrawingTool} magnet={drawingMagnet} onMagnetChange={setDrawingMagnet} onUndo={undoDrawing} onRedo={redoDrawing} canDelete={Boolean(selectedDrawingId)} onDelete={() => deleteDrawing(selectedDrawingId)} />
            <div className="chart-canvas-wrap"><ReplayChart bars={visibleBars} overlays={visibleIndicators} timeframe={timeframe} timeZone={timeZone} position={position} closedTrade={closedTrade} pendingOrder={pendingOrder} expanded={expanded} followReplay={followReplay} jumpToken={jumpToken} showVolume={showVolume} volumeStyle={volumeStyle} drawingTool={drawingTool} magnet={drawingMagnet} drawings={drawings} selectedDrawingId={selectedDrawingId} onSelectDrawing={setSelectedDrawingId} onDrawingsChange={applyDrawings} onDrawingToolChange={setDrawingTool} onPositionDrawing={usePositionDrawing} onUndoDrawing={undoDrawing} onRedoDrawing={redoDrawing} onDeleteDrawing={deleteDrawing} drawingMeta={{ created_at_replay_timestamp: currentBar?.timestamp || null, created_timeframe: timeframe }} /></div>
            {objectsOpen && <DrawingObjectPanel drawings={drawings} selectedId={selectedDrawingId} onSelect={(id) => { setSelectedDrawingId(id); setDrawingTool("cursor"); }} onToggleVisible={(id) => toggleDrawing(id, "visible")} onToggleLock={(id) => toggleDrawing(id, "locked")} onDelete={deleteDrawing} onPatch={patchDrawing} onClose={() => setObjectsOpen(false)} />}
          </div>
          {paneIndicators.length > 0 && <div className="mt-2 flex flex-wrap gap-2">{paneIndicators.map((item) => { const value = currentBar ? currentValue(item, currentBar.timestamp) : null; return <span key={item.id} className="rounded bg-stone-100 px-2 py-1 text-xs"><span style={{ color: item.color }}>●</span> {indicatorLabel(item, indicators, symbol)}: <strong>{value == null ? "—" : value.toFixed(3)}</strong></span>; })}</div>}
        </div>
        <div className="space-y-3">
          <div className="rounded-lg border border-stone-200 p-4">
            <div className="flex items-center justify-between"><h4 className="text-sm font-semibold">Indicators</h4><select className="rounded-md border border-stone-300 px-2 py-1 text-xs" defaultValue="" onChange={(e) => { addIndicator(e.target.value); e.target.value = ""; }}><option value="">+ Add indicator</option>{indicators.filter((item) => item.causal).map((item) => <option key={item.key} value={item.key}>{item.key === "volume" && symbol === "XAUUSD" ? "Tick Volume · OANDA activity" : item.name}</option>)}</select></div>
            <div className="mt-3 space-y-2">{selectedIndicators.map((item) => {
              const data = indicatorData[item.id]; const value = currentBar && data ? currentValue(data, currentBar.timestamp) : null;
              const displayValue = value == null ? "—" : item.key === "volume" ? Intl.NumberFormat("en-GB", { notation: "compact", maximumFractionDigits: 1 }).format(value) : value.toFixed(3);
              return <div key={item.id} className="rounded bg-stone-50 p-2 text-xs"><div className="flex items-center gap-2"><button title={item.visible ? "Hide" : "Show"} onClick={() => patchIndicator(item.id, { visible: !item.visible })} className="w-6">{item.visible ? "👁" : "○"}</button><span className="h-3 w-3 rounded-full" style={{ backgroundColor: item.color }} /><span className="font-medium">{indicatorLabel(item, indicators, symbol)}</span><span className="ml-auto tabular-nums text-stone-600">{displayValue}</span><button title="Settings" onClick={() => setEditingIndicatorId(editingIndicatorId === item.id ? null : item.id)}>⚙</button><button title="Remove" onClick={() => { setSelectedIndicators((old) => old.filter((x) => x.id !== item.id)); setEditingIndicatorId(null); }} className="text-red-700">🗑</button></div>
                {editingIndicatorId === item.id && <IndicatorSettings symbol={symbol} item={item} spec={indicators.find((spec) => spec.key === item.key)} onParam={(key, value) => patchIndicatorParam(item.id, key, value)} onPatch={(patch) => patchIndicator(item.id, patch)} />}
              </div>;
            })}</div>
            <p className="mt-2 text-[11px] text-stone-500">Eye hides without deleting. Volume now behaves like an indicator instead of a separate Replay toggle. Settings change indicator inputs/style. The 12-colour palette is assigned per instance; colours repeat only after the palette is exhausted.</p>
          </div>

          <div className="rounded-lg border border-stone-200 p-4"><h4 className="text-sm font-semibold">Order ticket</h4><p className="mt-1 text-[11px] text-stone-500">Risk, planned R:R and realised R are calculated from the actual fill, stop, target and exit; they are not manual inputs.</p>
            <div className="mt-3 grid grid-cols-2 gap-3"><Field label="Order type"><select className="input" value={orderType} onChange={(e) => setOrderType(e.target.value)}><option value="market">Market · next bar open</option><option value="limit">Limit · at price</option><option value="stop">Stop entry · at price</option></select></Field><Field label="Position value · USD"><input type="number" className="input" value={positionAmount} onChange={(e) => setPositionAmount(e.target.value)} /></Field>
              {orderType !== "market" && <Field label="Entry price"><input type="number" step="any" className="input" value={entryPrice} onChange={(e) => setEntryPrice(e.target.value)} placeholder="Price" /></Field>}
              <Field label="Stop loss"><input type="number" step="any" className="input" value={stop} onChange={(e) => setStop(e.target.value)} /></Field><Field label="Take profit"><input type="number" step="any" className="input" value={target} onChange={(e) => setTarget(e.target.value)} /></Field><Field label="Setup"><input className="input" value={setup} onChange={(e) => setSetup(e.target.value)} placeholder="Optional" /></Field></div>
            {!position && !pendingOrder && <div className="mt-3 grid grid-cols-2 gap-2"><button disabled={!nextBar || !atFrontier} onClick={() => placeOrder("long")} className="rounded-md bg-emerald-700 px-3 py-2 text-xs font-medium text-white disabled:opacity-40">BUY / LONG</button><button disabled={!nextBar || !atFrontier} onClick={() => placeOrder("short")} className="rounded-md bg-red-700 px-3 py-2 text-xs font-medium text-white disabled:opacity-40">SELL / SHORT</button></div>}
            {pendingOrder && <div className="mt-3 rounded bg-amber-50 p-3 text-xs text-amber-900"><strong>{pendingOrder.direction.toUpperCase()} {pendingOrder.order_type.toUpperCase()}</strong>{pendingOrder.entry_price != null ? ` @ ${money(pendingOrder.entry_price)}` : " · next bar open"}. Stop {money(pendingOrder.stop_loss)} · target {money(pendingOrder.take_profit)}. <button onClick={() => setPendingOrder(null)} className="ml-2 underline">Cancel order</button></div>}
            {position && <div className="mt-3 rounded bg-blue-50 p-3 text-xs text-blue-900"><div><strong>{position.direction.toUpperCase()}</strong> · entry {money(position.entry_price)} · qty {position.quantity.toFixed(4)}</div><div className="mt-1">Stop {money(position.stop_loss)} · target {money(position.take_profit)}</div><div className="mt-1">Initial risk <strong>{money(metrics.risk)}</strong> · Planned R:R <strong>{metrics.rr == null ? "—" : `${metrics.rr.toFixed(2)}:1`}</strong> · MFE/share {money(position.mfe_per_share)} · MAE/share {money(position.mae_per_share)}</div><button disabled={!nextBar} onClick={() => setPendingClose(true)} className="mt-2 underline">{pendingClose ? "Manual close queued for next bar open" : "Close manually on next bar open"}</button></div>}
            {closedTrade && <div className={`mt-3 rounded p-3 text-xs ${closedTrade.net_pnl >= 0 ? "bg-emerald-50 text-emerald-900" : "bg-red-50 text-red-900"}`}><strong>Closed:</strong> {closedTrade.exit_reason} · {money(closedTrade.exit_price)} · P&L {money(closedTrade.net_pnl)}</div>}
            {journalStatus && <p className="mt-2 text-xs text-stone-600">{journalStatus}</p>}
          </div>
          <Field label="Display timezone"><select className="input" value={timeZone} onChange={(e) => setTimeZone(e.target.value)}>{TIMEZONE_OPTIONS.map((zone) => <option key={zone.value} value={zone.value}>{zone.label}</option>)}</select></Field>
        </div>
      </div>
      <p className="mt-3 text-xs text-stone-500">Shortcuts: Space play/pause · → next bar · Shift+→ +5 · ← review one previously revealed bar. With a drawing selected: Ctrl/Cmd+C copy · Ctrl/Cmd+V paste · Delete remove · Ctrl/Cmd+Z/Y undo/redo. Rewinding marks the session as review mode and order entry stays disabled until you return to the reveal frontier.</p>
    </div>
  </div>;

  return <section className="replay-page-section mt-4 rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
    <div className="flex flex-wrap items-start justify-between gap-4"><div><h3 className="font-semibold">Historical Replay · workspace</h3><p className="mt-1 max-w-4xl text-xs text-stone-500">Replay can span days or months while future bars remain hidden. Context and replay horizon are separate: load as much prior structure as you need, then move continuously through later sessions.</p></div><button onClick={resumeCheckpoint} className="rounded-md border border-stone-300 px-3 py-2 text-xs">Resume saved replay</button></div>
    <div className="mt-3"><WatchlistBar compact onSelect={(ticker) => { setSymbol(ticker); setSymbolInput(ticker); if (String(ticker).toUpperCase() === "XAUUSD") setSession("24h"); else if (session === "24h") setSession("regular"); }} /></div>
    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
      <Field label="Symbol"><SymbolSearch value={symbolInput} onChange={setSymbolInput} onSelect={(item) => { setSymbol(item.ticker); setSymbolInput(item.ticker); if (String(item.ticker).toUpperCase() === "XAUUSD") setSession("24h"); else if (session === "24h") setSession("regular"); }} placeholder="AAPL" /></Field>
      <Field label="Replay starts"><input type="date" className="input" value={replayDate} onChange={(e) => { setReplayDate(e.target.value); if (replayEndDate < e.target.value) setReplayEndDate(addDays(e.target.value, 7)); }} /></Field>
      <Field label="Replay through"><input type="date" className="input" value={replayEndDate} onChange={(e) => setReplayEndDate(e.target.value)} /></Field>
      <Field label="Start time · ET"><input type="time" className="input" value={startTime} onChange={(e) => setStartTime(e.target.value)} /></Field>
      <Field label="Timeframe"><select className="input" value={timeframe} onChange={(e) => switchTimeframe(e.target.value)}>{TIMEFRAMES.map((tf) => <option key={tf}>{tf}</option>)}</select></Field>
      <Field label="Session"><select className="input" value={session} onChange={(e) => setSession(e.target.value)}><option value="regular">Regular</option><option value="extended">Extended</option><option value="24h">24h / full market</option></select></Field>
      <Field label="Historical context"><select className="input" value={contextMode} onChange={(e) => setContextMode(e.target.value)}><option value="1d">1 calendar day</option><option value="5d">~5 trading days</option><option value="1m">1 month</option><option value="3m">3 months</option><option value="custom">Custom bars</option></select></Field>
      <div className="flex items-end"><button disabled={loading} onClick={load} className="w-full rounded-md bg-stone-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50">{loading ? "Loading…" : "Load replay"}</button></div>
    </div>
    {contextMode === "custom" && <div className="mt-3 max-w-xs"><Field label="Custom context bars"><input type="number" min="0" max="50000" className="input" value={contextBars} onChange={(e) => setContextBars(e.target.value)} /></Field></div>}
    {checkpointStatus && <p className="mt-3 text-xs text-stone-600">{checkpointStatus}</p>}
    {workspace}
  </section>;
}

function orderFill(bar, order) {
  const o = Number(bar.open), h = Number(bar.high), l = Number(bar.low); const p = Number(order.entry_price);
  if (order.order_type === "market") return o;
  if (order.order_type === "limit") {
    if (order.direction === "long") { if (o <= p) return o; if (l <= p) return p; }
    else { if (o >= p) return o; if (h >= p) return p; }
  }
  if (order.order_type === "stop") {
    if (order.direction === "long") { if (o >= p) return o; if (h >= p) return p; }
    else { if (o <= p) return o; if (l <= p) return p; }
  }
  return null;
}
function validProtection(position) {
  if (position.direction === "long") {
    if (position.stop_loss != null && position.stop_loss >= position.entry_price) return false;
    if (position.take_profit != null && position.take_profit <= position.entry_price) return false;
  } else {
    if (position.stop_loss != null && position.stop_loss <= position.entry_price) return false;
    if (position.take_profit != null && position.take_profit >= position.entry_price) return false;
  }
  return true;
}
function indicatorLabel(item, specs, symbol = "") {
  const spec = specs.find((candidate) => candidate.key === item.key);
  const params = item.params || {};
  const primary = params.length ?? (item.key.startsWith("macd") ? `${params.fast ?? 12}/${params.slow ?? 26}` : null);
  const base = item.key === "volume" && String(symbol).toUpperCase() === "XAUUSD" ? "Tick Volume" : (spec?.name || item.key.toUpperCase());
  return `${base}${primary != null ? ` ${primary}` : ""}`;
}
function IndicatorSettings({ item, spec, onParam, onPatch, symbol }) {
  const defaults = spec?.defaults || {};
  if (item.key === "volume") return <div className="mt-2 rounded border border-stone-200 bg-white p-3"><p className="font-semibold">{String(symbol).toUpperCase() === "XAUUSD" ? "Tick Volume · OANDA activity" : "Volume settings"}</p><div className="mt-2 grid grid-cols-3 gap-2"><Field label="Up bars"><input type="color" value={item.upColor || "#34d399"} onChange={(e) => onPatch({ upColor: e.target.value })}/></Field><Field label="Down bars"><input type="color" value={item.downColor || "#f87171"} onChange={(e) => onPatch({ downColor: e.target.value })}/></Field><Field label="Opacity"><input type="number" min="0.05" max="1" step="0.05" className="input" value={item.volumeOpacity ?? .28} onChange={(e) => onPatch({ volumeOpacity: Number(e.target.value) })}/></Field></div><p className="mt-2 text-xs text-stone-500">Pane height and volume MA will arrive with the shared lower-pane system.</p></div>;
  return <div className="mt-2 rounded border border-stone-200 bg-white p-3"><p className="font-semibold">Indicator settings</p><div className="mt-2 grid grid-cols-2 gap-2">{Object.entries(defaults).map(([key, defaultValue]) => <Field key={key} label={key.replaceAll("_", " ")}>{key === "source" ? <select className="input" value={item.params?.[key] ?? defaultValue} onChange={(e) => onParam(key, e.target.value)}>{["close","open","high","low"].map((value) => <option key={value}>{value}</option>)}</select> : typeof defaultValue === "boolean" ? <select className="input" value={String(item.params?.[key] ?? defaultValue)} onChange={(e) => onParam(key, e.target.value === "true")}><option value="true">Yes</option><option value="false">No</option></select> : <input type={typeof defaultValue === "number" ? "number" : "text"} step="any" className="input" value={item.params?.[key] ?? defaultValue} onChange={(e) => onParam(key, typeof defaultValue === "number" ? Number(e.target.value) : e.target.value)} />}</Field>)}</div><div className="mt-3"><p className="text-[10px] font-medium uppercase tracking-wide text-stone-500">Colour</p><div className="mt-1 flex flex-wrap gap-1">{INDICATOR_COLORS.map((color) => <button key={color} title={color} onClick={() => onPatch({ color })} className={`h-5 w-5 rounded-full border ${item.color === color ? "ring-2 ring-stone-900" : "border-stone-300"}`} style={{ backgroundColor: color }} />)}</div></div><Field label="Line width"><select className="input" value={item.lineWidth || 2} onChange={(e) => onPatch({ lineWidth: Number(e.target.value) })}><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="4">4</option></select></Field></div>;
}
function Field({ label, children }) { return <label className="block"><span className="mb-1 block text-[10px] font-medium uppercase tracking-wide text-stone-500">{label}</span>{children}</label>; }
