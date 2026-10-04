import {navigationState,navigationKey,tradeReference,detailWindow} from './reviewNavigation.js';
import {createSectionCache} from './runSections.js';
const reviewCache=createSectionCache((id,args)=>api.tradeReview(id,...JSON.parse(args)),6,60000);
import { useEffect, useRef, useState } from "react";
import { CandlestickSeries, LineSeries, ColorType, HistogramSeries, createChart, createSeriesMarkers } from "lightweight-charts";
import { api } from "../../api/client";
import { TIMEZONE_OPTIONS, resolvedZone } from "../../utils/timezones";

const TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"];
function seconds(value) { return Math.floor(new Date(value).getTime() / 1000); }
function money(value) { return value == null ? "—" : `$${Number(value).toFixed(2)}`; }
function r(value) { return value == null ? "—" : `${Number(value) >= 0 ? "+" : ""}${Number(value).toFixed(2)}R`; }
function rr(value) { return value == null ? "—" : `${Number(value).toFixed(2)}:1`; }
function formatDate(value, zone) {
  return new Intl.DateTimeFormat("en-GB", { timeZone: resolvedZone(zone), dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}
function chartTime(time, zone, withDate = false) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: resolvedZone(zone),
    ...(withDate ? { day: "2-digit", month: "short" } : {}),
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).format(new Date(Number(time) * 1000));
}

export default function TradeAuditChart({ trade, run, tradeIndex, timeframe: initialTimeframe, session: initialSession, onClose, navigationTrades=[], onNavigate, capture=null }) {
  const [bars, setBars] = useState([]);
  const [auditMeta, setAuditMeta] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [timeframe, setTimeframe] = useState(initialTimeframe || "5m");
  const [session, setSession] = useState(initialSession || "regular");
  const [timeZone, setTimeZone] = useState("America/New_York");
  const [beforeBars, setBeforeBars] = useState(50);
  const [afterBars, setAfterBars] = useState(capture ? 25 : 20);
  const [extendedHistory,setExtendedHistory]=useState(Boolean(capture));
  const [showResearch,setShowResearch]=useState(false);
  const [showEvidence,setShowEvidence]=useState(true);
  const [showVolume, setShowVolume] = useState(true);
  const [showLevels, setShowLevels] = useState(true);
  const [showMarkers, setShowMarkers] = useState(true);
  const [showReasoning, setShowReasoning] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const ref = useRef(null);

  const navigation=navigationState(navigationTrades,trade);
  useEffect(()=>{if(!onNavigate)return;const handler=event=>{const key=navigationKey(event);if(key&&navigation[key]){event.preventDefault();onNavigate(navigation[key]);}};window.addEventListener('keydown',handler);return()=>window.removeEventListener('keydown',handler)},[navigation.previous,navigation.next,onNavigate]);
  useEffect(()=>{if(!capture&&onNavigate)document.getElementById('trade-review-navigation')?.scrollIntoView({block:'start'});},[trade]);
  useEffect(()=>{if(capture&&!loading&&(error||!bars.length))capture.done({review:auditMeta?.review||{},images:[],warning:error||'Historical candles unavailable; not recorded.'});},[loading,error,bars,auditMeta,capture]);
  useEffect(() => { setTimeframe(initialTimeframe || "5m"); }, [initialTimeframe]);
  useEffect(() => { setSession(initialSession || "regular"); }, [initialSession]);

  useEffect(() => {
    const requestedBefore = Math.max(0, Math.min(500, Number(beforeBars) || 0));
    const requestedAfter = Math.max(0, Math.min(200, Number(afterBars) || 0));
    let stale=false;setLoading(true);setError("");setAuditMeta(null);
    const timer = globalThis.setTimeout(async () => {
      try{
        let data;
        if(run?.saved_run?.id!=null&&tradeIndex>=0){
          data=await reviewCache.get(run.saved_run.id,JSON.stringify([tradeIndex,requestedBefore,requestedAfter,extendedHistory]));
          if(timeframe!==initialTimeframe||session!==initialSession){const chart=await api.strategyLabAuditBars(data.symbol,timeframe,session,trade.entry_time,trade.exit_time,requestedBefore,requestedAfter);data={...data,...chart,review:data.review};}
        }else data=await api.strategyLabAuditBars(trade.symbol,timeframe,session,trade.entry_time,trade.exit_time,requestedBefore,requestedAfter);
        if(!stale){setBars(data.bars||[]);setAuditMeta(data)}
      }catch(e){if(!stale)setError(e.message)}finally{if(!stale)setLoading(false)}
    }, 150);
    return () => {stale=true;globalThis.clearTimeout(timer)};
  }, [trade, run?.saved_run?.id, tradeIndex, timeframe, session, beforeBars, afterBars, extendedHistory]);

  useEffect(() => {
    if (loading || !ref.current || !bars.length) return undefined;
    const chart = createChart(ref.current, {
      autoSize: true, height: expanded ? Math.max(650, globalThis.innerHeight - 250) : 500,
      layout: { background: { type: ColorType.Solid, color: getComputedStyle(document.documentElement).getPropertyValue("--ledger-chart-background").trim() || "#111111" }, textColor: "#a8a29e" },
      grid: { vertLines: { color: getComputedStyle(document.documentElement).getPropertyValue("--ledger-chart-grid").trim() || "#262626" }, horzLines: { color: getComputedStyle(document.documentElement).getPropertyValue("--ledger-chart-grid").trim() || "#262626" } },
      rightPriceScale: { borderColor: "#333333" },
      timeScale: {
        borderColor: "#333333", timeVisible: true, secondsVisible: false, minBarSpacing: 0.000001,
        tickMarkFormatter: (time) => timeframe === "1d" && trade.metadata?.strategy_version === "momentum_vcp_breakout_baseline_v1"
          ? new Intl.DateTimeFormat("en-GB", { timeZone: resolvedZone(timeZone), day: "2-digit", month: "short" }).format(new Date(Number(time) * 1000))
          : chartTime(time, timeZone, false),
      },
      localization: { timeFormatter: (time) => chartTime(time, timeZone, true) },
      crosshair: { vertLine: { color: "#737373" }, horzLine: { color: "#737373" } },
    });
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: getComputedStyle(document.documentElement).getPropertyValue("--ledger-candle-up").trim() || "#22c55e", downColor: getComputedStyle(document.documentElement).getPropertyValue("--ledger-candle-down").trim() || "#ef4444", borderVisible: false,
      wickUpColor: getComputedStyle(document.documentElement).getPropertyValue("--ledger-candle-up").trim() || "#22c55e", wickDownColor: getComputedStyle(document.documentElement).getPropertyValue("--ledger-candle-down").trim() || "#ef4444",
    });
    let volume = null;
    if (showVolume) {
      volume = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "", priceLineVisible: false });
      volume.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    }
    const seen = new Set();
    const clean = bars.map((bar) => ({
      time: seconds(bar.timestamp), open: Number(bar.open), high: Number(bar.high), low: Number(bar.low), close: Number(bar.close), volume: Number(bar.volume || 0),
    })).filter((bar) => Number.isFinite(bar.time) && !seen.has(bar.time) && seen.add(bar.time)).sort((a, b) => a.time - b.time);
    const highlights=new Map((auditMeta?.review?.highlights||[]).map(h=>[seconds(h.timestamp),h.kind]));
    candles.setData(clean.map(({volume:_,...bar})=>showEvidence&&highlights.has(bar.time)?{...bar,color:highlights.get(bar.time)==='entry'?'#38bdf8':'#fbbf24',wickColor:highlights.get(bar.time)==='entry'?'#38bdf8':'#fbbf24'}:bar));
    if(showEvidence||showResearch){
      let pane=0;
      const palette=['#60a5fa','#a78bfa','#a78bfa','#fbbf24'];
      for(const [index,series] of (auditMeta?.review?.series||[]).entries()){
        if(series.role==='research_only'?!showResearch:!showEvidence)continue;
        const line=chart.addSeries(LineSeries,{color:palette[index%palette.length],lineWidth:series.id.includes('_upper')||series.id.includes('_lower')?1:2,title:series.label,priceLineVisible:false,lastValueVisible:false},series.overlay?0:++pane);
        const points=series.points||[];let cursor=-1;const output=[];
        const minutes={'1m':1,'5m':5,'15m':15,'30m':30,'1h':60,'4h':240,'1d':1440}[timeframe];
        for(const bar of clean){while(cursor+1<points.length&&seconds(points[cursor+1].available_at)<=bar.time+minutes*60)cursor++;if(cursor>=0&&seconds(points[cursor].timestamp)<=bar.time+minutes*60)output.push({time:bar.time,value:points[cursor].value});}
        line.setData(output);
      }
    }
    if (volume) volume.setData(clean.map((bar) => ({ time: bar.time, value: bar.volume, color: bar.close >= bar.open ? "rgba(34,197,94,.30)" : "rgba(239,68,68,.30)" })));

    if (showLevels) {
      const meta = trade.metadata || {};
      const levels = [
        [trade.entry_price, meta.entry_retrace != null ? `Entry · ${Math.round(Number(meta.entry_retrace) * 100)}%` : "Entry", 2, 0],
        [trade.stop_loss, "Stop", 1, 2],
        [trade.take_profit, "Target", 1, 2],
        [trade.exit_price, "Exit", 1, 2],
        [meta.liquidity_level, "1H Liquidity", 1, 2],
        [meta.swing_level_broken, "Type 3 Swing", 1, 2],
        [meta.impulse_high, "Impulse High", 1, 3],
        [meta.impulse_low, "Impulse Low", 1, 3],
        [meta.pivot, "Base pivot", 2, 2],
        [meta.base_low, "Base low", 1, 3],
        [meta.or_high, "Opening range high", 1, 2],
        [meta.or_low, "Opening range low", 1, 2],
      ];
      for(const level of auditMeta?.review?.levels||[])levels.push([level.value,level.label,1,2]);
      const seenLevels = new Set();
      levels.forEach(([price, title, lineWidth, lineStyle]) => {
        if (price == null || !Number.isFinite(Number(price))) return;
        const key = `${Number(price).toFixed(8)}:${title}`;
        if (seenLevels.has(key)) return;
        seenLevels.add(key);
        candles.createPriceLine({ price: Number(price), title, lineWidth, lineStyle, axisLabelVisible: true });
      });
    }

    const nearest = (target) => {
      if (!clean.length) return null;
      return clean.reduce((best, bar) => Math.abs(bar.time - target) < Math.abs(best.time - target) ? bar : best, clean[0]).time;
    };
    if (showMarkers) {
      const meta = trade.metadata || {};
      const markers = [];
      for (const [stamp, label] of [[meta.base_start, "BASE START"], [meta.base_end, "BASE END"], [meta.breakout_time, "BREAKOUT"], [meta.range_start, "RANGE START"], [meta.range_end, "RANGE END"], [meta.excursion_start, "EXCURSION"], [meta.excursion_start && meta.confirmation_bar_time, "VWAP REENTRY"]]) {
        if (!stamp) continue;
        const time = nearest(seconds(stamp));
        if (time != null) markers.push({ time, position: "aboveBar", shape: "circle", color: "#a78bfa", text: label });
      }
      const entryTime = nearest(seconds(trade.entry_time));
      const exitTime = nearest(seconds(meta.exit_bar_time || trade.exit_time));
      if (entryTime != null) markers.push({
        time: entryTime, position: trade.direction === "long" ? "belowBar" : "aboveBar",
        shape: trade.direction === "long" ? "arrowUp" : "arrowDown", color: "#60a5fa", text: `ENTRY ${money(trade.entry_price)}`,
      });
      if (exitTime != null) markers.push({
        time: exitTime, position: trade.direction === "long" ? "aboveBar" : "belowBar",
        shape: trade.direction === "long" ? "arrowDown" : "arrowUp", color: trade.result === "win" ? "#22c55e" : "#ef4444", text: `EXIT ${r(trade.r_multiple)}`,
      });
      if (meta.sweep_time) {
        const time = nearest(seconds(meta.sweep_time));
        if (time != null) markers.push({ time, position: trade.direction === "long" ? "belowBar" : "aboveBar", shape: "circle", color: "#f59e0b", text: "SWEEP" });
      }
      if (meta.swing_level_time) {
        const time = nearest(seconds(meta.swing_level_time));
        if (time != null) markers.push({ time, position: trade.direction === "long" ? "aboveBar" : "belowBar", shape: "circle", color: "#06b6d4", text: "TYPE 3 SWING" });
      }
      if (meta.type3_confirmation_time) {
        const time = nearest(seconds(meta.type3_confirmation_time));
        if (time != null) markers.push({ time, position: trade.direction === "long" ? "belowBar" : "aboveBar", shape: "circle", color: "#8b5cf6", text: "TYPE 3 ✓" });
      }
      for (const partial of meta.partial_exits || []) {
        const partialTime = nearest(seconds(partial.timestamp));
        if (partialTime != null) markers.push({
          time: partialTime, position: trade.direction === "long" ? "aboveBar" : "belowBar",
          shape: "circle", color: "#a16207", text: `PARTIAL ${Number(partial.fraction_of_remaining || 0) * 100}%`,
        });
      }
      for(const window of auditMeta?.config?.entry_windows||[]){
        for(const [clock,label] of [[window.start,'ENTRY WINDOW'],[window.end,'WINDOW END']]){
          for(const bar of clean){const parts=Object.fromEntries(new Intl.DateTimeFormat('en-GB',{timeZone:'America/New_York',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(bar.time*1000)).map(p=>[p.type,p.value]));if(`${parts.hour}:${parts.minute}`===clock)markers.push({time:bar.time,position:'belowBar',shape:'circle',color:'#64748b',text:label});}
        }
      }
      markers.sort((a, b) => a.time - b.time);
      if (markers.length) createSeriesMarkers(candles, markers);
    }
    chart.timeScale().fitContent();
    let disposed=false;
    if(capture){
      const settle=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      (async()=>{try{await settle();if(disposed)return;const images=[];
        for(const kind of ['full','entry','exit']){
          if(kind==='exit'&&!capture.exit)continue;
          if(kind==='full')chart.timeScale().fitContent();
          else {const window=detailWindow(clean.map(b=>({timestamp:new Date(b.time*1000).toISOString()})),kind==='entry'?trade.entry_time:trade.exit_time,kind==='entry'?40:15,kind==='entry'?25:20);if(window)chart.timeScale().setVisibleLogicalRange(window);}
          await settle();if(disposed)return;
          const canvas=chart.takeScreenshot();images.push({kind,width:canvas.width,height:canvas.height,data:canvas.toDataURL('image/jpeg',.95)});
        }
        if(!disposed)capture.done({review:auditMeta?.review||{},images});
      }catch(e){if(!disposed)capture.done({review:auditMeta?.review||{},images:[],warning:e.message});}})();
    }
    return () => {disposed=true;chart.remove()};
  }, [bars, trade, loading, showVolume, showLevels, showMarkers, timeZone, expanded, showEvidence, showResearch, auditMeta, timeframe]);

  const body = <>
    {onNavigate&&<div id="trade-review-navigation" className="ui-toolbar sticky top-0 z-10 bg-white p-3" aria-label="Trade review navigation">
      <button className="mini-btn" disabled={!navigation.previous} onClick={()=>onNavigate(navigation.previous)}>Previous trade (J)</button>
      <strong>{navigation.index<0?'Outside current filters':`Trade ${navigation.index+1} of ${navigation.count} filtered trades`}</strong>
      <button className="mini-btn" disabled={!navigation.next} onClick={()=>onNavigate(navigation.next)}>Next trade (K)</button>
      <span>{tradeReference(run?.saved_run?.id??'unsaved',tradeIndex)}</span>
      <label>Jump to trade <select className="input" value={navigation.index} onChange={e=>onNavigate(navigationTrades[Number(e.target.value)])}><option value={-1} disabled>Select trade</option>{navigationTrades.map((t,i)=><option key={i} value={i}>#{run.trades.indexOf(t)+1} {t.symbol} {t.entry_time} {t.direction}</option>)}</select></label>
    </div>}
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <p className="text-xs uppercase tracking-wide text-stone-500">Trade audit · historical bars</p>
        <h3 className="mt-1 text-lg font-semibold">{trade.symbol} · {trade.direction.toUpperCase()} · {r(trade.r_multiple)}</h3>
        <p className="mt-1 text-xs text-stone-500">Entry {formatDate(trade.entry_time, timeZone)} · Exit {formatDate(trade.exit_time, timeZone)} · {String(trade.exit_reason).replaceAll("_", " ")}</p>
      </div>
      <div className="flex gap-2">
        <button onClick={() => setExpanded((value) => !value)} className="rounded-md border border-stone-300 px-3 py-2 text-xs font-medium">{expanded ? "Exit full screen" : "Expand"}</button>
        <button onClick={onClose} className="rounded-md border border-stone-300 px-3 py-2 text-xs font-medium">Close chart</button>
      </div>
    </div>

    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
      <Mini label="Signal" value={String(trade.signal_reason || "—").replaceAll("_", " ")} />
      <Mini label="Entry" value={money(trade.entry_price)} />
      <Mini label="Stop" value={money(trade.stop_loss)} />
      <Mini label="Target" value={money(trade.take_profit)} />
      <Mini label="Actual exit" value={money(trade.exit_price)} />
      <Mini label="Planned R:R" value={rr(trade.planned_rr)} />
      <Mini label="Realised R" value={r(trade.r_multiple)} />
      <Mini label="Net P&L" value={money(trade.net_pnl)} />
    </div>
    <div className="mt-3 grid gap-3 sm:grid-cols-3">
      <Mini label="Quantity" value={trade.quantity == null ? "—" : Number(trade.quantity).toFixed(4)} />
      <Mini label="Initial risk" value={money(trade.initial_risk_amount)} />
      <Mini label="Duration" value={trade.duration_minutes == null ? "—" : `${Number(trade.duration_minutes).toFixed(0)} min`} />
    </div>
    {(trade.metadata?.partial_exits?.length > 0 || trade.metadata?.final_stop_loss != null) && <div className="mt-3 rounded-lg border border-stone-200 bg-stone-50 p-3 text-xs text-stone-600"><strong>Strategy management:</strong> {trade.metadata?.partial_exits?.length || 0} partial exit{(trade.metadata?.partial_exits?.length || 0) === 1 ? "" : "s"}{trade.metadata?.final_stop_loss != null ? ` · final stop ${money(trade.metadata.final_stop_loss)}` : ""}{trade.metadata?.final_take_profit != null ? ` · final target ${money(trade.metadata.final_take_profit)}` : ""}. Planned R:R above still uses the original stop/target.</div>}

    <div className="mt-4 grid gap-3 lg:grid-cols-4 xl:grid-cols-8">
      <Field label="Chart timeframe"><select className="input" value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>{TIMEFRAMES.map((tf) => <option key={tf}>{tf}</option>)}</select></Field>
      <Field label="Timezone"><select className="input" value={timeZone} onChange={(e) => setTimeZone(e.target.value)}>{TIMEZONE_OPTIONS.map((zone) => <option key={zone.value} value={zone.value}>{zone.label}</option>)}</select></Field>
      <Field label="Session"><select className="input" value={session} onChange={(e) => setSession(e.target.value)}><option value="24h">24h / full provider session</option><option value="regular">US regular</option><option value="extended">US extended</option></select></Field>
      <Field label="Bars before"><input type="number" min="5" max="500" className="input" value={beforeBars} onChange={(e) => setBeforeBars(e.target.value)} /></Field>
      <Field label="Bars after"><input type="number" min="5" max="200" className="input" value={afterBars} onChange={(e) => setAfterBars(e.target.value)} /></Field>
      <Toggle label={String(trade.symbol).toUpperCase() === "XAUUSD" ? "Tick volume" : "Volume"} value={showVolume} onChange={setShowVolume} />
      <Toggle label="Price levels" value={showLevels} onChange={setShowLevels} />
      <Toggle label="Strategy markers" value={showMarkers} onChange={setShowMarkers} />
    </div>
    {auditMeta && <p className="mt-2 text-xs text-stone-500">Context loaded: {auditMeta.actual_before_bars ?? 0} bars before entry · {auditMeta.actual_after_bars ?? 0} bars after exit · {auditMeta.count ?? bars.length} displayed bars total.</p>}

    {showReasoning && <Reasoning trade={trade} />}
    <button onClick={() => setShowReasoning((value) => !value)} className="mt-3 text-xs font-medium underline">{showReasoning ? "Hide" : "Show"} strategy reasoning</button>

    {auditMeta?.review&&<section className="ui-section" aria-label="Trade decision evidence"><div className="ui-toolbar"><h3>Strategy evidence</h3>{auditMeta.review.series.some(s=>s.role==='research_only')&&<label><input type="checkbox" checked={showResearch} onChange={e=>setShowResearch(e.target.checked)}/> Research overlays (not used by strategy)</label>}{auditMeta.review.extended_available&&<label><input type="checkbox" checked={extendedHistory} onChange={e=>setExtendedHistory(e.target.checked)}/> Reconstruct extended indicator history (slower first load)</label>}<label><input type="checkbox" checked={showEvidence} onChange={e=>setShowEvidence(e.target.checked)}/> Show historical series and confirmation candles</label></div><p className="text-xs">Blue candles: entry confirmation. Amber: exit confirmation. Volume is research only unless explicitly declared by the strategy. Dynamic indicators are never replaced by horizontal signal values.</p>
      <div className="ui-toolbar">{auditMeta.review.series.map(series=><span className="text-xs" key={series.id}>{series.label} / {series.timeframe} / {series.role==='research_only'?'Research only':'Strategy evidence'} / reconstructed</span>)}</div>
      {auditMeta.review.warnings.map((warning,i)=><p className="text-xs muted" key={i}>{warning}</p>)}
      <div className="grid gap-4 lg:grid-cols-2">{['entry','exit'].map(group=><details open key={group}><summary>{group==='entry'?'Why this trade entered':'Why this trade exited'}</summary><dl className="text-xs space-y-2 mt-2">{auditMeta.review.evidence[group].map((field,i)=><div key={i} className="flex flex-wrap justify-between gap-2"><dt>{field.label}</dt><dd>{field.value==null?'Not recorded':Array.isArray(field.value)?field.value.map(v=>typeof v==='object'?`${v.start}-${v.end}`:String(v)).join(', '):String(field.value)} <span className="muted">/ {field.provenance.replaceAll('_',' ')}</span> {field.status&&<strong>{field.status}</strong>}</dd></div>)}</dl></details>)}</div></section>}
      {loading && <div className="mt-4 flex h-[300px] items-center justify-center bg-stone-950 text-sm text-stone-300">Loading audit candles…</div>}
    {error && <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
    {!loading && !error && <div ref={ref} className={expanded ? "mt-4 h-[calc(100vh-250px)] min-h-[650px] w-full overflow-hidden rounded-lg" : "mt-4 h-[500px] w-full overflow-hidden rounded-lg"} />}
    <p className="mt-3 text-xs text-stone-500">Times are displayed in the selected timezone; stored timestamps remain UTC. The chart uses the same {timeframe} / {session} market-data path as the backtest. “Bars before/after” now counts displayed session-filtered candles rather than wall-clock minutes. Markers attach to the nearest displayed OHLCV bar, so exact intrabar execution time cannot be recovered from bar data alone.</p>
  </>;

  return <section className={expanded ? "fixed inset-3 z-50 overflow-auto rounded-xl border border-stone-300 bg-white p-5 shadow-2xl" : "mt-5 rounded-xl border border-stone-300 bg-white p-5 shadow-sm"}>{body}</section>;
}

function Reasoning({ trade }) {
  const metadata = trade.metadata || {};
  const rows = Object.entries(metadata).filter(([, value]) => value !== null && value !== undefined && typeof value !== "object");
  return <div className="mt-4 rounded-lg border border-stone-200 bg-stone-50 p-4">
    <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Why Ledger entered</p>
    <p className="mt-2 text-sm"><strong>Signal:</strong> {String(trade.signal_reason || "unspecified").replaceAll("_", " ")}</p>
    {rows.length > 0 ? <div className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-2 lg:grid-cols-4">{rows.map(([key, value]) => <div key={key} className="text-xs"><span className="text-stone-500">{key.replaceAll("_", " ")}</span><div className="mt-0.5 font-medium">{typeof value === "number" ? Number(value).toFixed(4).replace(/0+$/, "").replace(/\.$/, "") : String(value)}</div></div>)}</div> : <p className="mt-2 text-xs text-stone-500">This strategy did not attach additional signal metadata. New strategy plugins can provide values/levels here without changing the backtest engine.</p>}
  </div>;
}
function Mini({ label, value }) { return <div className="rounded-lg bg-stone-50 p-3"><p className="text-[10px] uppercase tracking-wide text-stone-500">{label}</p><p className="mt-1 text-sm font-medium">{value}</p></div>; }
function Field({ label, children }) { return <label className="block"><span className="mb-1 block text-[10px] font-medium uppercase tracking-wide text-stone-500">{label}</span>{children}</label>; }
function Toggle({ label, value, onChange }) { return <label className="flex min-h-[60px] items-center gap-2 rounded-md border border-stone-200 px-3 text-xs"><input type="checkbox" checked={value} onChange={(e) => onChange(e.target.checked)} />{label}</label>; }
