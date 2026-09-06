import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import SymbolSearch from "../../components/SymbolSearch";
import WatchlistBar from "../../components/WatchlistBar";
import ChartDrawingToolbar from "../../components/chart/ChartDrawingToolbar";
import DrawingObjectPanel from "../../components/chart/DrawingObjectPanel";
import { loadDrawings, saveDrawings } from "../../components/chart/drawingStore";
import { useWatchlist } from "../../app/watchlist";
import PriceChart from "../research/PriceChart";
import ResearchPage from "../research/ResearchPage";

const TF = ["1m","5m","15m","30m","1h","4h","1d"];
const INITIAL_LOOK = {"1m":93,"5m":186,"15m":186,"30m":186,"1h":365,"4h":730,"1d":1825};
const MAX_LOOK = {"1m":365,"5m":1095,"15m":1825,"30m":1825,"1h":3650,"4h":5000,"1d":5000};
const COLORS = ["#60a5fa","#f59e0b","#a78bfa","#22c55e","#f43f5e","#06b6d4","#e879f9","#84cc16","#fb7185","#38bdf8","#facc15","#c084fc"];
let indicatorSeq = 0;

function makeIndicator(spec, index) {
  return { id:`chart-ind-${Date.now()}-${indicatorSeq++}`, key:spec.key, name:spec.name, overlay:Boolean(spec.overlay), params:{...(spec.defaults||{})}, visible:true, color:COLORS[index%COLORS.length], lineWidth:2 };
}
function historyLabel(days){ if(days>=365)return `${(days/365).toFixed(days%365===0?0:1)}y loaded`; return `${Math.round(days/30)}mo loaded`; }

export default function ChartsPage({selectedTicker="AAPL",onTickerChange}){
  const [mode,setMode]=useState("charts");
  const [layout,setLayout]=useState(1);
  const [tf,setTf]=useState(()=>localStorage.getItem("ledger.chartTimeframe")||"5m");
  const [session,setSession]=useState(()=>localStorage.getItem("ledger.chartSession")||"regular");
  const [zone]=useState(()=>localStorage.getItem("ledger.timeZone")||"America/New_York");
  const [symbols,setSymbols]=useState([selectedTicker,"NVDA","MSFT","SPY"]);
  const [indicatorSpecs,setIndicatorSpecs]=useState([]);
  const [expandedIndex,setExpandedIndex]=useState(null);
  const [layoutFullscreen,setLayoutFullscreen]=useState(false);
  const visible=symbols.slice(0,layout);

  useEffect(()=>{ api.strategyLabIndicators().then((r)=>setIndicatorSpecs(r.items||r.indicators||r||[])).catch(()=>setIndicatorSpecs([])); },[]);
  useEffect(()=>{ if(selectedTicker && symbols[0]!==selectedTicker) setSymbols((items)=>[selectedTicker,...items.slice(1)]); },[selectedTicker]);
  useEffect(()=>{ localStorage.setItem("ledger.chartTimeframe",tf); },[tf]);
  useEffect(()=>{ localStorage.setItem("ledger.chartSession",session); },[session]);
  useEffect(()=>{
    const handler=(event)=>{ if(event.key!=="Escape")return; if(expandedIndex!=null)setExpandedIndex(null); else if(layoutFullscreen)setLayoutFullscreen(false); };
    globalThis.addEventListener("keydown",handler); return()=>globalThis.removeEventListener("keydown",handler);
  },[expandedIndex,layoutFullscreen]);

  const change=(i,sym)=>{const next=[...symbols];next[i]=sym;setSymbols(next);if(i===0)onTickerChange?.(sym)};
  const selectWatch=(sym)=>{ const index=expandedIndex ?? 0; change(index,sym); };

  const workspace=<div className={layoutFullscreen?"chart-layout-fullscreen":"chart-workspace-shell"}>
    <div className="chart-global-toolbar">
      <div className="chart-toolbar-group"><span className="toolbar-label">Layout</span>{[1,2,4].map(n=><button key={n} onClick={()=>setLayout(n)} className={`chart-toolbar-btn ${layout===n?"active":""}`}>{n}</button>)}</div>
      <div className="chart-toolbar-group"><span className="toolbar-label">Timeframe</span>{TF.map(x=><button key={x} onClick={()=>setTf(x)} className={`chart-toolbar-btn ${tf===x?"active":""}`}>{x}</button>)}</div>
      <select className="chart-select ml-auto" value={session} onChange={e=>setSession(e.target.value)}><option value="regular">Regular</option><option value="extended">Extended</option></select>
      <button className="chart-toolbar-btn" onClick={()=>setLayoutFullscreen(v=>!v)} title="Fit the complete selected layout to the screen">{layoutFullscreen?"Exit layout full screen":"Full layout ⛶"}</button>
    </div>
    <div className={`multi-chart-workspace layout-${layout} ${expandedIndex!=null?"has-expanded":""}`}>
      {visible.map((sym,i)=><ChartPanel key={i} index={i} symbol={sym} onSymbolChange={(value)=>change(i,value)} timeframe={tf} onTimeframeChange={setTf} layout={layout} onLayoutChange={setLayout} session={session} zone={zone} indicatorSpecs={indicatorSpecs} expanded={expandedIndex===i} onExpand={()=>setExpandedIndex(expandedIndex===i?null:i)} />)}
    </div>
  </div>;

  return <div className="chart-page-root">
    <div className="chart-page-header">
      <div><p className="eyebrow">Market workspace</p><h2>Charts</h2><p>Multi-chart analysis with shared chart tools, indicators and persistent drawings.</p></div>
      <div className="chart-mode-switch"><button className={`mini-btn ${mode==="charts"?"active-btn":""}`} onClick={()=>setMode("charts")}>Multi-chart</button><button className={`mini-btn ${mode==="research"?"active-btn":""}`} onClick={()=>setMode("research")}>Company research</button></div>
    </div>
    {mode==="research"?<div className="mt-4"><ResearchPage selectedTicker={selectedTicker} onTickerChange={onTickerChange}/></div>:<>
      {!layoutFullscreen&&<WatchlistBar onSelect={selectWatch} compact />}
      {workspace}
    </>}
  </div>;
}

function ChartPanel({index,symbol,onSymbolChange,timeframe,onTimeframeChange,layout,onLayoutChange,session,zone,indicatorSpecs,expanded,onExpand}) {
  const watchlist=useWatchlist();
  const [bars,setBars]=useState([]);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState("");
  const [tool,setTool]=useState("cursor");
  const [magnet,setMagnet]=useState(()=>localStorage.getItem("ledger.drawingMagnet")||"weak");
  const [objectsOpen,setObjectsOpen]=useState(false);
  const [selectedDrawingId,setSelectedDrawingId]=useState(null);
  const [drawings,setDrawings]=useState(()=>loadDrawings("charts",symbol));
  const [history,setHistory]=useState([]);
  const [redo,setRedo]=useState([]);
  const [indicators,setIndicators]=useState([]);
  const [indicatorDefaultsReady,setIndicatorDefaultsReady]=useState(false);
  const [indicatorData,setIndicatorData]=useState({});
  const [indicatorPicker,setIndicatorPicker]=useState("");
  const [editingIndicator,setEditingIndicator]=useState(null);
  const [historyDays,setHistoryDays]=useState(()=>({}));
  const lookbackDays=historyDays[timeframe]||INITIAL_LOOK[timeframe]||365;
  const maxLookback=MAX_LOOK[timeframe]||5000;

  useEffect(()=>{ setDrawings(loadDrawings("charts",symbol)); setHistory([]);setRedo([]);setSelectedDrawingId(null); },[symbol]);
  useEffect(()=>{ if(indicatorDefaultsReady||!indicatorSpecs.length)return; const volume=indicatorSpecs.find(x=>x.key==="volume"); if(volume)setIndicators([makeIndicator(volume,0)]); setIndicatorDefaultsReady(true); },[indicatorSpecs,indicatorDefaultsReady]);
  useEffect(()=>{ saveDrawings("charts",symbol,drawings); },[symbol,drawings]);
  useEffect(()=>{ let cancelled=false; setLoading(true);setError(""); api.researchBars(symbol,timeframe,lookbackDays,false,session).then(r=>{if(!cancelled)setBars(r.bars||[])}).catch(e=>{if(!cancelled)setError(e.message)}).finally(()=>{if(!cancelled)setLoading(false)}); return()=>{cancelled=true}; },[symbol,timeframe,session,lookbackDays]);

  useEffect(()=>{
    if(!indicators.length)return;
    let cancelled=false;
    const active=indicators.filter(x=>x.key!=="volume");
    Promise.all(active.map(async item=>{
      const sig=JSON.stringify([symbol,timeframe,session,lookbackDays,item.key,item.params]);
      if(indicatorData[item.id]?._signature===sig)return null;
      try{const data=await api.researchIndicator(symbol,item.key,timeframe,lookbackDays,session,item.params);return [item.id,{...data,_signature:sig}]}catch{return [item.id,{values:[],_signature:sig,error:true}]}
    })).then(entries=>{if(cancelled)return;setIndicatorData(current=>{const next={...current};entries.filter(Boolean).forEach(([id,data])=>{next[id]=data});return next})});
    return()=>{cancelled=true};
  },[symbol,timeframe,session,lookbackDays,indicators]);

  const overlays=useMemo(()=>indicators.filter(x=>x.visible!==false&&x.overlay).map(item=>({...item,values:indicatorData[item.id]?.values||[],label:indicatorLabel(item)})),[indicators,indicatorData]);
  const showVolume=indicators.some(x=>x.key==="volume"&&x.visible!==false) || !indicators.length;
  const currentNonOverlay=indicators.filter(x=>x.visible!==false&&!x.overlay&&x.key!=="volume").map(item=>{const values=indicatorData[item.id]?.values||[];return {...item,current:values.length?Number(values[values.length-1].value):null}});

  const applyDrawings=(next,meta={})=>{if(meta.checkpoint){setHistory(h=>[...h.slice(-49),drawings]);setRedo([]);return;}if(meta.transient){setDrawings(next);return;}setHistory(h=>[...h.slice(-49),drawings]);setRedo([]);setDrawings(next)};
  const undo=()=>{if(!history.length)return;const previous=history[history.length-1];setRedo(r=>[drawings,...r]);setHistory(h=>h.slice(0,-1));setDrawings(previous)};
  const redoOne=()=>{if(!redo.length)return;const next=redo[0];setHistory(h=>[...h,drawings]);setRedo(r=>r.slice(1));setDrawings(next)};
  const deleteDrawing=(id)=>{if(!id)return;applyDrawings(drawings.filter(x=>x.id!==id));if(selectedDrawingId===id)setSelectedDrawingId(null)};
  const toggleDrawing=(id,key)=>applyDrawings(drawings.map(x=>x.id===id?{...x,[key]:!x[key]}:x));
  const patchDrawing=(id,patch)=>applyDrawings(drawings.map(x=>x.id===id?{...x,...patch}:x));

  const addIndicator=(key)=>{const spec=indicatorSpecs.find(x=>x.key===key);if(!spec)return;setIndicators(items=>[...items,makeIndicator(spec,items.length)]);setIndicatorPicker("")};
  const updateIndicator=(id,patch)=>setIndicators(items=>items.map(x=>x.id===id?{...x,...patch}:x));
  const updateIndicatorParam=(id,key,value)=>setIndicators(items=>items.map(x=>x.id===id?{...x,params:{...x.params,[key]:numericMaybe(value)}}:x));
  const loadMoreHistory=()=>{
    if(loading||lookbackDays>=maxLookback)return;
    setHistoryDays(current=>({...current,[timeframe]:Math.min(maxLookback,Math.max(lookbackDays+INITIAL_LOOK[timeframe],lookbackDays*2))}));
  };

  const panel=<section className={`market-chart-panel ${expanded?"expanded-chart-panel":""}`}>
    <header className="market-chart-header">
      <button type="button" className={`favorite-btn ${watchlist.has(symbol)?"active":""}`} onClick={()=>watchlist.toggle(symbol)} title={watchlist.has(symbol)?"Remove from watchlist":"Add to watchlist"}>★</button>
      <div className="chart-symbol-search"><SymbolSearch value={symbol} onChange={(v)=>onSymbolChange(v.toUpperCase())} onSelect={(x)=>onSymbolChange(x.ticker)}/></div>
      <span className="chart-timeframe-badge">{timeframe}</span>
      <span className="chart-history-badge" title="Scroll near the left edge to load more history">{historyLabel(lookbackDays)}{lookbackDays<maxLookback?" · scroll left for more":""}</span>
      {expanded && <div className="expanded-chart-controls"><div className="chart-toolbar-group compact">{TF.map(x=><button key={x} onClick={()=>onTimeframeChange?.(x)} className={`chart-toolbar-btn ${timeframe===x?"active":""}`}>{x}</button>)}</div><div className="chart-toolbar-group compact">{[1,2,4].map(n=><button key={n} onClick={()=>onLayoutChange?.(n)} className={`chart-toolbar-btn ${layout===n?"active":""}`}>{n}×</button>)}</div></div>}
      <div className="indicator-picker-wrap"><select className="chart-select" value={indicatorPicker} onChange={e=>{setIndicatorPicker(e.target.value);addIndicator(e.target.value)}}><option value="">＋ Indicators</option>{indicatorSpecs.map(x=><option key={x.key} value={x.key}>{x.name}</option>)}</select></div>
      <button className={`chart-icon-btn ${objectsOpen?"active":""}`} title="Object panel" onClick={()=>setObjectsOpen(v=>!v)}>☷</button>
      <button className="chart-icon-btn" title={expanded?"Restore layout":"Maximise chart"} onClick={onExpand}>{expanded?"↙":"⛶"}</button>
    </header>
    <div className="indicator-strip">
      {indicators.map(item=><div key={item.id} className="indicator-chip" style={{"--indicator-color":item.color}}><span className="indicator-dot"/><span>{indicatorLabel(item)}</span><button title={item.visible===false?"Show":"Hide"} onClick={()=>updateIndicator(item.id,{visible:item.visible===false})}>{item.visible===false?"○":"●"}</button><button title="Settings" onClick={()=>setEditingIndicator(editingIndicator===item.id?null:item.id)}>⚙</button><button title="Remove" onClick={()=>setIndicators(xs=>xs.filter(x=>x.id!==item.id))}>×</button></div>)}
      {currentNonOverlay.map(item=><span key={`value-${item.id}`} className="indicator-value-chip">{indicatorLabel(item)} {item.current==null?"—":item.current.toFixed(2)}</span>)}
    </div>
    {editingIndicator&&<IndicatorSettings item={indicators.find(x=>x.id===editingIndicator)} onChange={patch=>updateIndicator(editingIndicator,patch)} onParam={(k,v)=>updateIndicatorParam(editingIndicator,k,v)} onClose={()=>setEditingIndicator(null)}/>} 
    <div className="chart-stage">
      <ChartDrawingToolbar tool={tool} onToolChange={setTool} magnet={magnet} onMagnetChange={setMagnet} onUndo={undo} onRedo={redoOne} canDelete={Boolean(selectedDrawingId)} onDelete={()=>deleteDrawing(selectedDrawingId)}/>
      <div className="chart-canvas-wrap">
        {loading&&!bars.length?<div className="chart-loading">Loading {symbol}…</div>:error?<div className="chart-error">{error}</div>:<PriceChart bars={bars} overlays={overlays} timeZone={zone} height={400} fill expanded={expanded} showVolume={showVolume} drawingTool={tool} magnet={magnet} drawings={drawings} selectedDrawingId={selectedDrawingId} onSelectDrawing={setSelectedDrawingId} onDrawingsChange={applyDrawings} onDrawingToolChange={setTool} onUndoDrawing={undo} onRedoDrawing={redoOne} onDeleteDrawing={deleteDrawing} onNeedMoreHistory={loadMoreHistory}/>} 
        {loading&&bars.length>0&&<div className="chart-history-loading">Loading more history…</div>}
      </div>
      {objectsOpen&&<DrawingObjectPanel drawings={drawings} selectedId={selectedDrawingId} onSelect={(id)=>{setSelectedDrawingId(id);setTool("select")}} onToggleVisible={(id)=>toggleDrawing(id,"visible")} onToggleLock={(id)=>toggleDrawing(id,"locked")} onDelete={deleteDrawing} onPatch={patchDrawing} onClose={()=>setObjectsOpen(false)}/>} 
    </div>
  </section>;
  return expanded?<div className="chart-expanded-backdrop">{panel}</div>:panel;
}

function indicatorLabel(item){const p=item.params||{};if(p.length)return `${item.name||item.key} ${p.length}`;return item.name||item.key}
function numericMaybe(value){if(value==="")return "";const n=Number(value);return Number.isFinite(n)&&String(value).trim()!==""?n:value}
function IndicatorSettings({item,onChange,onParam,onClose}){
  if(!item)return null;return <div className="indicator-settings-popover"><div className="indicator-settings-head"><strong>{indicatorLabel(item)}</strong><button onClick={onClose}>×</button></div><div className="indicator-settings-grid">{Object.entries(item.params||{}).map(([key,value])=><label key={key}><span>{key}</span><input className="input" value={value} onChange={e=>onParam(key,e.target.value)}/></label>)}<label><span>Line colour</span><input type="color" value={item.color} onChange={e=>onChange({color:e.target.value})}/></label><label><span>Line width</span><input type="number" min="1" max="5" className="input" value={item.lineWidth} onChange={e=>onChange({lineWidth:Number(e.target.value)})}/></label></div></div>
}
