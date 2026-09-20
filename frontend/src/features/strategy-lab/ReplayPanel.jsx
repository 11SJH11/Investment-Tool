import ReplayOrderTicket from "./ReplayOrderTicket.jsx";
import {loadPreferences} from "../../app/preferences.js";
import ReplayToolbar from "./ReplayToolbar.jsx";
import {useReplayPlayback} from "./useReplayPlayback.js";
import {jumpCursor} from "./replayControls.js";
import {useWorkflow} from "../../app/WorkflowContext.js";
import { replayEconomics, replaySource, replayRollAction } from "./futures-utils";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/client";
import SymbolSearch from "../../components/SymbolSearch";
import { TIMEZONE_OPTIONS, resolvedZone } from "../../utils/timezones";
import ReplayChart from "./ReplayChart";
import FuturesProvenance from '../../components/FuturesProvenance';
import WatchlistBar from "../../components/WatchlistBar";
import ChartDrawingToolbar from "../../components/chart/ChartDrawingToolbar";
import DrawingObjectPanel from "../../components/chart/DrawingObjectPanel";
import { loadDrawings, saveDrawings } from "../../components/chart/drawingStore";

const TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h"];
import {INDICATOR_COLORS,daysAgo,addDays,money,fmt,nyDate,currentValue,countThroughTimestamp,indicatorRequestSignature,contextArgs,makeIndicator,plannedMetrics} from "./replayHelpers.js";

export default function ReplayPanel({ indicators = [], onError }) {
  const {context:workflow}=useWorkflow();
  const handoff=workflow?.target==="Replay"?workflow:null;
  const preferences=useMemo(()=>loadPreferences(),[]);
  const busy = useRef(false);
  const initialDate = handoff?.start_date||daysAgo(30);
  const [symbol, setSymbol] = useState(handoff?.symbol||"AAPL");
  const [symbolInput, setSymbolInput] = useState(handoff?.symbol||"AAPL");
  const [replayDate, setReplayDate] = useState(initialDate);
  const [replayEndDate, setReplayEndDate] = useState(handoff?.end_date||addDays(initialDate, 7));
  const [startTime, setStartTime] = useState(handoff?.start_time||"09:30");
  const [timeframe, setTimeframe] = useState(() => handoff?.timeframe || (TIMEFRAMES.includes(localStorage.getItem("ledger.chartTimeframe"))?localStorage.getItem("ledger.chartTimeframe"):"5m"));
  const [session, setSession] = useState(handoff?.symbol&&(/!$/.test(handoff.symbol)||handoff.symbol==="XAUUSD")?"24h":"regular");
  const [contextMode, setContextMode] = useState(preferences.replayContext||"5d");
  const [contextBars, setContextBars] = useState(500);
  const [timeZone, setTimeZone] = useState("America/New_York");
  const [dataset, setDataset] = useState(null);
  const [visibleCount, setVisibleCount] = useState(0);
  const [furthestVisibleCount, setFurthestVisibleCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(Number(preferences.replaySpeed)||1);
  const [expanded, setExpanded] = useState(false);
  const [followReplay, setFollowReplay] = useState(Boolean(preferences.replayFollow));
  const [jumpToken, setJumpToken] = useState(0);
  const [integrityCompromised, setIntegrityCompromised] = useState(false);
  const [selectedIndicators, setSelectedIndicators] = useState([]);
  const [indicatorDefaultsInitialised, setIndicatorDefaultsInitialised] = useState(false);
  const [indicatorData, setIndicatorData] = useState({});
  const [editingIndicatorId, setEditingIndicatorId] = useState(null);
  const [contracts, setContracts] = useState("1");
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

  const bars = (dataset?.timeline || []).map((timestamp, i) => dataset.source_bars[i] || { timestamp });
  const visibleBars = dataset?.bars || [];
  const currentBar = dataset?.source_bars?.at(-1);
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
    if (!activeSymbol || busy.current) return;
    busy.current = true;
    setLoading(true); setPlaying(false); onError?.(""); setJournalStatus("");
    try {
      const response = await api.strategyLabReplayBars(
        activeSymbol, config.replayDate, config.replayEndDate, config.startTime,
        config.timeframe, config.session, config.contextBars, config.contextDays, restore?.anchorTimestamp || null,
      );
      setSymbol(activeSymbol); setSymbolInput(activeSymbol); setTimeframe(config.timeframe); setSession(config.session); setDataset({...response, config: {...config, symbol: activeSymbol}}); setIndicatorData({});
      const initial = response.initial_visible_count || 1;
      const restoredVisible = restore?.anchorTimestamp
        ? countThroughTimestamp(response.timeline.map(timestamp => ({timestamp})), restore.anchorTimestamp, initial)
        : response.visible_count || initial;
      const frontierCount = restore?.frontierTimestamp
        ? countThroughTimestamp(response.timeline.map(timestamp => ({timestamp})), restore.frontierTimestamp, restoredVisible)
        : restore ? Number(restore.furthestVisibleCount || restoredVisible) : initial;
      const restoredFurthest = Math.min(Math.max(restoredVisible, frontierCount), response.timeline.length);
      setVisibleCount(restoredVisible); setFurthestVisibleCount(restoredFurthest);
      setPosition(restore?.position || null); setClosedTrade(null); setPendingOrder(restore?.pendingOrder || null); setPendingClose(Boolean(restore?.pendingClose));
      setIntegrityCompromised(Boolean(restore?.integrityCompromised));
      setFollowReplay(restore?.followReplay ?? false);
      if (!restore?.preserveViewport) setJumpToken((value) => value + 1);
    } catch (error) { onError?.(error.message || String(error)); }
    finally { setLoading(false); busy.current = false; }
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
      { ...dataset.config, timeframe: nextTimeframe },
      {
        visibleCount, furthestVisibleCount, anchorTimestamp, frontierTimestamp,
        position, pendingOrder, pendingClose, integrityCompromised, followReplay, preserveViewport: true,
      },
    );
  };

  useEffect(() => {
    if (!dataset || !selectedIndicators.length) return;
    let cancelled = false;
    const {symbol, replayDate, replayEndDate, startTime, timeframe, session, ...context} = dataset.config;
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
          context.contextBars, context.contextDays, item.params, dataset.frontier,
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


  useEffect(() => { if (finished) setPlaying(false); }, [finished]);

  const closeTrade = async (exitPriceValue, exitTime, reason, pos = position) => {
    if (!pos) return;
    const mult = pos.direction === "long" ? 1 : -1;
    const gross = (Number(exitPriceValue) - pos.entry_price) * mult * pos.quantity * (pos.contract_multiplier || 1);
    const trade = { ...pos, exit_price: Number(exitPriceValue), exit_time: exitTime, exit_reason: reason, net_pnl: gross };
    setClosedTrade(trade); setPosition(null); setPendingClose(false);
    if(preferences.replayAutoJournal!==false)await saveTradeToJournal(trade);
    else setJournalStatus("Auto-journal is off. Save this closed trade before starting another.");
  };

  const saveTradeToJournal=async trade=>{
    if(!trade)return;
    const {symbol,replayDate,replayEndDate,startTime,timeframe,session}=dataset.config;
    const reason=trade.exit_reason;
    try {
      const externalId = [
        "replay", symbol, replayDate, startTime, timeframe, trade.direction,
        trade.entry_time, trade.exit_time, Number(trade.entry_price).toFixed(6), Number(trade.exit_price).toFixed(6),
      ].join(":");
      const saved = await api.createJournalTrade({
        source: "replay", name: `Replay · ${symbol}`, account: "Replay", ticker: symbol,
        direction: trade.direction, opened_at: trade.entry_time, closed_at: trade.exit_time,
        entry_price: trade.entry_price, exit_price: trade.exit_price, quantity: trade.quantity,
        position_amount: dataset?.instrument?.asset_type === "future" ? null : Number(trade.position_amount || positionAmount || 0) || null, position_currency: "USD",
        stop_loss: trade.stop_loss, take_profit: trade.take_profit, fees: 0,
        trade_type: "replay", setup: trade.setup || setup, entry_timeframe: timeframe,
        external_provider: "ledger_replay", external_id: externalId,
        source_metadata: {
          contract_multiplier: trade.contract_multiplier || 1, source_contract: trade.source_contract || null,
          displayed_symbol: symbol, executed_contract: trade.source_contract || null,
          continuous_alias: trade.continuous_alias || '', provider: trade.provider,
          roll_schedule_version: trade.roll_schedule_version, adjustment_mode: 'raw', adjustment_method: 'none', price_adjustment: 0,
          replay_date: replayDate, replay_end_date: replayEndDate, start_time: startTime,
          timeframe, session, integrity: integrityCompromised ? "review_rewound" : "clean",
          exit_reason: reason, mfe_per_share: Number(trade.mfe_per_share || 0), mae_per_share: Number(trade.mae_per_share || 0),
        },
        notes: `Replay exit: ${reason}. Integrity: ${integrityCompromised ? "review/rewound" : "clean"}. MFE/share: ${Number(trade.mfe_per_share || 0).toFixed(4)}. MAE/share: ${Number(trade.mae_per_share || 0).toFixed(4)}.`,
      });
      setJournalStatus(`${saved.deduplicated ? "Already in" : "Saved to"} Journal as replay trade #${saved.id}. Add reasoning/screenshots there when you review it.`);
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
    if (!dataset || count <= 0 || busy.current) return;
    busy.current = true; setLoading(true);
    try {
    let cursor = visibleCount;
    const targetCursor = Math.min(bars.length, cursor + count);
    if (targetCursor === cursor) return;
    const {symbol, replayDate, replayEndDate, startTime, timeframe, session, ...context} = dataset.config;
    const response = await api.strategyLabReplayBars(symbol, replayDate, replayEndDate, startTime,
      timeframe, session, context.contextBars, context.contextDays, bars[targetCursor-1].timestamp);
    const revealedSource = response.source_bars;
    if (cursor < furthestVisibleCount) cursor = Math.min(targetCursor, furthestVisibleCount);
    const remaining = targetCursor - cursor;
    if (dataset.instrument?.asset_type === "future" && position && !position.contract_multiplier) throw new Error("This legacy futures Replay position predates contract accounting. Start a new Replay session.");
    let active = position;
    let order = pendingOrder;
    let closeQueued = pendingClose;
    for (let i = 0; i < remaining && cursor < bars.length; i += 1) {
      const bar = revealedSource[cursor];
      let rollAction;
      try { rollAction = replayRollAction(dataset.instrument,bar,active,order); }
      catch (error) {
        // Keep the last processed frontier; never display later prices from the
        // larger advance response after terminating on a roll.
        if (cursor > visibleCount) {
          const partial = await api.strategyLabReplayBars(symbol,replayDate,replayEndDate,startTime,timeframe,session,context.contextBars,context.contextDays,bars[cursor-1].timestamp);
          setDataset({...partial,config:dataset.config});setVisibleCount(cursor);setFurthestVisibleCount(old=>Math.max(old,cursor));
        }
        setIntegrityCompromised(true);setPendingOrder(null);setPendingClose(false);
        throw error;
      }
      if (rollAction === 'cancel_order') { order=null;setPendingOrder(null);onError?.('Pending order cancelled at contract roll; place a new order for the active contract.'); }
      if (order && !active) {
        const fill = orderFill(bar, order);
        if (fill != null) {
          const amount = Number(order.position_amount || 0);
          const economics = replayEconomics(dataset.instrument, amount, fill, [order.stop_loss, order.take_profit],bar);
          const candidate = {
            direction: order.direction, entry_price: fill, entry_time: bar.timestamp, ...economics, source_contract: bar.source_contract,
            continuous_alias: bar.continuous_alias, provider: bar.provider, roll_schedule_version: bar.roll_schedule_version,
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
    setDataset({...response, config: dataset.config}); setIndicatorData({});
    setVisibleCount(cursor); setFurthestVisibleCount((old) => Math.max(old, cursor));
    } catch (error) { setPlaying(false); onError?.(error.message); }
    finally { busy.current = false; setLoading(false); }
  };

  const rewindOne = async () => {
    if (!dataset || visibleCount <= (dataset.initial_visible_count || 1)) return;
    if (position || pendingOrder || pendingClose) { onError?.("Close/cancel the active replay trade or order before rewinding."); return; }
    const cursor = Math.max(dataset.initial_visible_count || 1, visibleCount - 1);
    await fetchReplay(dataset.config, {
      anchorTimestamp: bars[cursor-1].timestamp, frontierTimestamp: bars[furthestVisibleCount-1].timestamp,
      integrityCompromised: true, followReplay: false, preserveViewport: true,
    });
  };

  const jumpNextSession = async () => {
    if (!currentBar) return;
    const currentDate = nyDate(currentBar.timestamp);
    const nextIndex = bars.findIndex((bar, index) => index >= visibleCount && nyDate(bar.timestamp) !== currentDate);
    if (nextIndex >= 0) await advance(nextIndex - visibleCount + 1);
  };

  const placeOrder = (direction) => {
    if (busy.current || !dataset || !nextBar || !atFrontier) { onError?.("Return to the newest revealed candle before placing a replay order."); return; }
    const explicitEntry = orderType === "market" ? null : Number(entryPrice);
    if (orderType !== "market" && (!Number.isFinite(explicitEntry) || explicitEntry <= 0)) { onError?.("Enter a valid order price for limit/stop entry."); return; }
    const isFuture = dataset.instrument?.asset_type === "future";
    const amount = Number((isFuture ? contracts : positionAmount) || 0);
    if (isFuture) {
      try { replayEconomics(dataset.instrument, amount, explicitEntry ?? Number(currentBar.close), [stop === "" ? null : Number(stop), target === "" ? null : Number(target)],currentBar); }
      catch (error) { onError?.(error.message); return; }
    }
    if (!(amount > 0)) { onError?.("Position value must be greater than zero."); return; }
    if(preferences.replayConfirm&& !confirm(`Queue ${direction.toUpperCase()} ${orderType} replay order?`))return;
    setPendingOrder({
      direction, order_type: orderType, entry_price: explicitEntry,
      stop_loss: stop === "" ? null : Number(stop), take_profit: target === "" ? null : Number(target),
      position_amount: amount, setup,
      source_contract: replaySource(dataset.instrument,currentBar),
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
    if (!dataset || busy.current) return;
    const payload = {
      config: dataset.config,
      anchorTimestamp: currentBar?.timestamp, frontierTimestamp: bars[furthestVisibleCount-1]?.timestamp,
      visibleCount, furthestVisibleCount, integrityCompromised, followReplay,
      selectedIndicators, position, pendingOrder, pendingClose, setup, positionAmount, orderType, entryPrice, stop, target,
    };
    localStorage.setItem("ledger.replay.checkpoint", JSON.stringify(payload)); setCheckpointStatus("Checkpoint saved in this browser.");
  };
  const resumeCheckpoint = async () => {
    const raw = localStorage.getItem("ledger.replay.checkpoint");
    if (!raw) { setCheckpointStatus("No saved Replay checkpoint found in this browser."); return; }
    try {
      if (busy.current) return;
      const saved = JSON.parse(raw); const cfg = saved.config || {};
      if (!saved.anchorTimestamp) throw new Error("This older checkpoint has no canonical frontier. Start a new Replay session.");
      setReplayDate(cfg.replayDate); setReplayEndDate(cfg.replayEndDate); setStartTime(cfg.startTime); setTimeframe(cfg.timeframe); setSession(cfg.session);
      setContextMode(cfg.contextDays === 1 ? "1d" : cfg.contextDays === 8 ? "5d" : cfg.contextDays === 31 ? "1m" : cfg.contextDays === 93 ? "3m" : "custom");
      if (cfg.contextBars != null) setContextBars(cfg.contextBars);
      setSelectedIndicators(saved.selectedIndicators || []); setSetup(saved.setup || ""); setPositionAmount(String(saved.positionAmount || "1000"));
      setOrderType(saved.orderType || "market"); setEntryPrice(saved.entryPrice || ""); setStop(saved.stop || ""); setTarget(saved.target || "");
      await fetchReplay(cfg, saved); setCheckpointStatus("Checkpoint resumed.");
    } catch (error) { setCheckpointStatus(`Could not resume checkpoint: ${error.message}`); }
  };

  const jumpTo = async stamp => {
    if(busy.current||!dataset)return;
    const cursor=jumpCursor(bars,stamp,dataset.initial_visible_count||1);
    if(cursor==null){onError?.('Choose a time inside the loaded replay period.');return;}
    setPlaying(false);
    if(cursor>=visibleCount){await advance(cursor-visibleCount);return;}
    if(position||pendingOrder||pendingClose){onError?.('Close/cancel the active replay trade or order before rewinding.');return;}
    await fetchReplay(dataset.config,{anchorTimestamp:bars[cursor-1].timestamp,frontierTimestamp:bars[furthestVisibleCount-1].timestamp,integrityCompromised:true,followReplay:false,preserveViewport:true});
  };
  useReplayPlayback({playing,speed:playbackSpeed,ready:Boolean(dataset),finished,actions:{
    next:()=>advance(1),five:()=>advance(5),previous:rewindOne,play:()=>setPlaying(v=>!v),
    buy:()=>document.querySelector('[data-replay-buy]')?.focus(),sell:()=>document.querySelector('[data-replay-sell]')?.focus(),
    limit:()=>setOrderType('limit'),close:()=>{if(position&&nextBar)setPendingClose(true);},
    escape:()=>{setDrawingTool('cursor');setSelectedDrawingId(null);setExpanded(false);}
  }});
  const workspace = dataset && <div className={expanded ? "fixed inset-0 z-50 overflow-auto bg-stone-100 p-3" : "mt-4"}>
    <div className={`rounded-xl border border-stone-200 bg-white ${expanded ? "min-h-[calc(100vh-24px)] p-3 shadow-2xl" : "p-4"}`}>
      <ReplayToolbar busy={loading} help={preferences.replayHelp!==false} title={`${symbol} ${timeframe} / ${fmt(currentBar?.timestamp,timeZone)}`} canPrevious={visibleCount>(dataset.initial_visible_count||1)&&!position&&!pendingOrder&&!pendingClose} canNext={Boolean(nextBar)} playing={playing} speed={playbackSpeed} setSpeed={setPlaybackSpeed} follow={followReplay} expanded={expanded} previous={rewindOne} next={()=>advance(1)} five={()=>advance(5)} togglePlay={()=>setPlaying(v=>!v)} nextSession={jumpNextSession} toggleFollow={()=>{setFollowReplay(v=>!v);setJumpToken(v=>v+1);}} current={()=>setJumpToken(v=>v+1)} save={saveCheckpoint} restart={()=>fetchReplay({symbol,replayDate,replayEndDate,startTime,timeframe,session,...context})} objects={()=>setObjectsOpen(v=>!v)} toggleExpanded={()=>setExpanded(v=>!v)} jump={jumpTo}/>
      {expanded&&<div className="ui-toolbar">{TIMEFRAMES.map(tf=><button key={tf} className="mini-btn" onClick={()=>switchTimeframe(tf)}>{tf}</button>)}</div>}
      <div className={`mt-3 rounded-md px-3 py-2 text-xs ${integrityCompromised ? "bg-amber-50 text-amber-900" : "bg-emerald-50 text-emerald-900"}`}>
        Replay integrity: <strong>{integrityCompromised ? "review mode · future bars were previously viewed" : "clean"}</strong>. Visible {visibleCount}/{bars.length}. {finished ? "End of loaded replay range." : `Loaded through ${dataset.replay_end_date}.`} <span className="ml-2 text-stone-500">Data: {dataset.provider ? `${dataset.provider} · ` : ""}{dataset.source_timeframe || timeframe}{String(dataset.aggregation||"").includes("aligned_from_1m") ? ` → ${timeframe}` : ""}{dataset.effective_session==="24h" ? " · 24h market" : ""}.</span>
        <FuturesProvenance bars={dataset.source_bars}/>
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

          {closedTrade&&<button className="mini-btn" onClick={()=>saveTradeToJournal(closedTrade)}>Save closed trade to Journal</button>}
          <ReplayOrderTicket {...{orderType,setOrderType,dataset,contracts,positionAmount,setContracts,setPositionAmount,entryPrice,setEntryPrice,stop,setStop,target,setTarget,setup,setSetup,position,pendingOrder,nextBar,atFrontier,placeOrder,setPendingOrder,currentBar,metrics,setPendingClose,pendingClose,closedTrade,journalStatus}}/>
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
