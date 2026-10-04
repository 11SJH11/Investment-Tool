import {useEffect,useMemo,useRef,useState} from 'react';
import {ColorType,LineSeries,CrosshairMode,createChart,createSeriesMarkers} from 'lightweight-charts';
import {resolvedZone} from '../../utils/timezones';
import {assignRunStyles,prepareCurve,unionDomain,pointAt,chartValue} from './equitySeries.js';

export default function PerformanceChart({points=[],startingBalance=0,runs=null,runStyles=null,mode='equity',expanded=false,timeZone='America/New_York',onTradeSelect=null}){
 const host=useRef(null),chartRef=useRef(null),seriesRef=useRef([]),legendRefs=useRef(new Map()),styles=useRef(runStyles||new Map()),hoverDate=useRef(null);
 const fullRange=useRef(true);
 const [hidden,setHidden]=useState(new Set()),[focus,setFocus]=useState(null);
 const input=useMemo(()=>runs||[{id:'single',name:'Performance',result:{equity_curve:points,metrics:{starting_balance:startingBalance}}}],[runs,points,startingBalance]);
 const curves=useMemo(()=>input.map(run=>({...prepareCurve(run.result?.equity_curve,run.result?.metrics?.starting_balance),id:String(run.id),label:`${run.id==='single'?'':`#${run.id} `}${run.name||run.result?.strategy?.name||'Run'}`,balance:run.result?.metrics?.starting_balance,currency:run.config?.account_currency||run.result?.account_currency||'account units'})),[input]);
 const domain=useMemo(()=>unionDomain(curves),[curves]);assignRunStyles(curves.map(c=>c.id),styles.current);
 const fmt=(value,suffix='')=>value==null?'Unavailable':`${Number(value).toLocaleString('en-GB',{maximumFractionDigits:2})}${suffix}`;
 const reset=()=>{fullRange.current=true;const chart=chartRef.current;if(!chart||!domain)return;chart.timeScale().fitContent();if(domain.from<domain.to)chart.timeScale().setVisibleRange(domain)};
 useEffect(()=>{
  if(!host.current||!domain)return;
  const css=getComputedStyle(document.documentElement),token=(key,fallback)=>css.getPropertyValue(key).trim()||fallback;
  const height=expanded?Math.max(560,innerHeight-230):540;
  const chart=createChart(host.current,{autoSize:true,height,layout:{background:{type:ColorType.Solid,color:token('--ledger-chart-background','#111111')},textColor:token('--ledger-muted','#a8a29e')},grid:{vertLines:{color:token('--ledger-chart-grid','#262626')},horzLines:{color:token('--ledger-chart-grid','#262626')}},timeScale:{minBarSpacing:0.000001,rightOffset:0,timeVisible:true,tickMarkFormatter:time=>new Intl.DateTimeFormat('en-GB',{timeZone:resolvedZone(timeZone),month:'short',year:'2-digit'}).format(new Date(Number(time)*1000))},crosshair:{mode:CrosshairMode.Normal},localization:{timeFormatter:time=>new Intl.DateTimeFormat('en-GB',{timeZone:resolvedZone(timeZone),dateStyle:'medium',timeStyle:'short'}).format(new Date(Number(time)*1000))}});
  chartRef.current=chart;
  chart.timeScale().subscribeVisibleTimeRangeChange(range=>{if(host.current&&range){host.current.dataset.visibleFrom=String(range.from);host.current.dataset.visibleTo=String(range.to)}});
  const pairs=[];const markers=new Map();
  for(const curve of curves){
   const style=styles.current.get(curve.id);
   const common={...style,lineWidth:2,priceLineVisible:false,lastValueVisible:curves.length===1,crosshairMarkerVisible:true};
   const equity=chart.addSeries(LineSeries,{...common,priceFormat:{type:'custom',minMove:.01,formatter:v=>fmt(v,mode==='return'?'%':mode==='r'?'R':'')}},0);
   const dd=chart.addSeries(LineSeries,{...common,priceFormat:{type:'custom',minMove:.01,formatter:v=>fmt(v,'%')},autoscaleInfoProvider:base=>{const info=base();if(info)info.priceRange.maxValue=0;return info;}},1);
   if(!pairs.length)dd.createPriceLine({price:0,title:'Drawdown 0%',color:token('--ledger-muted','#a8a29e'),lineWidth:1,lineStyle:2,axisLabelVisible:true});
   equity.setData(curve.display.map(p=>{const value=chartValue(p,mode,curve.balance);return value==null?{time:p.time}:{time:p.time,value}}));
   dd.setData(curve.display.map(p=>p.drawdown_pct==null?{time:p.time}:{time:p.time,value:Number(p.drawdown_pct)}));
   if(onTradeSelect){const list=[];for(const p of curve.display)for(const [i,t] of (p.closed_trades||[]).entries()){const id=`${curve.id}:${p.time}:${i}`;markers.set(id,t);list.push({id,time:p.time,position:'aboveBar',shape:'circle',color:style.color})}if(list.length)createSeriesMarkers(equity,list);}
   pairs.push({id:curve.id,equity,dd,style});
  }
  chart.panes()[0]?.setStretchFactor(7);chart.panes()[1]?.setStretchFactor(3);
  seriesRef.current=pairs;reset();
  let frame=0;
  const fitted=()=>{if(!host.current)return;const scale=chart.timeScale();host.current.dataset.startX=String(scale.timeToCoordinate(domain.from));host.current.dataset.endX=String(scale.timeToCoordinate(domain.to));host.current.dataset.plotWidth=String(scale.width())};
  const observer=new ResizeObserver(()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{frame=requestAnimationFrame(()=>{if(fullRange.current)reset();frame=requestAnimationFrame(fitted)})})});
  observer.observe(host.current);
  const manual=()=>{fullRange.current=false};const element=host.current;element.addEventListener('wheel',manual,{passive:true});element.addEventListener('pointerdown',manual);

  chart.subscribeCrosshairMove(event=>{
   if(hoverDate.current)hoverDate.current.textContent=event.time?new Intl.DateTimeFormat('en-GB',{timeZone:resolvedZone(timeZone),dateStyle:'medium',timeStyle:'short'}).format(new Date(Number(event.time)*1000)):'Hover either pane to inspect';
   for(const curve of curves){const el=legendRefs.current.get(curve.id);if(!el)continue;const p=event.time?pointAt(curve,Number(event.time)):null;el.textContent=p?`Equity ${fmt(p.equity)} / Return ${fmt(chartValue(p,'return',curve.balance),'%')} / DD ${fmt(p.drawdown_pct,'%')}${p.time!==Number(event.time)?' / prior observation':''}`:'No observation';}
  });
  if(onTradeSelect)chart.subscribeClick(event=>{const trade=markers.get(String(event.hoveredObjectId));if(trade)onTradeSelect(trade)});
  return()=>{observer.disconnect();cancelAnimationFrame(frame);element.removeEventListener("wheel",manual);element.removeEventListener("pointerdown",manual);chart.remove();chartRef.current=null;seriesRef.current=[]};
 },[curves,mode,expanded,timeZone,onTradeSelect,domain]);
 useEffect(()=>{for(const pair of seriesRef.current){const options={visible:!hidden.has(pair.id),color:focus&&focus!==pair.id?pair.style.color+'35':pair.style.color,lineWidth:focus===pair.id?3:2};pair.equity.applyOptions(options);pair.dd.applyOptions(options)}},[hidden,focus,curves,mode,expanded,timeZone,onTradeSelect]);
 return <section className="performance-workspace" aria-label="Equity and drawdown history"><div className="ui-toolbar"><strong>{mode==='return'?'Normalized return (%)':mode==='r'?'Cumulative R':'Equity (account units)'} / Drawdown (%)</strong><button className="mini-btn" onClick={reset}>Full range / Reset zoom</button><button className="mini-btn" onClick={()=>{setHidden(new Set());setFocus(null)}}>Show all runs</button></div>
 <p className="text-xs muted">Saved account equity and running-peak drawdown. Separate runs retain their own dates and capital. {mode==='return'?'Returns use each run’s starting balance.':'Compare different capitals using normalized return; verify account currencies before comparing absolute equity.'} Zoom/pan in either pane; both share one time axis.</p>
 <div className="performance-layout"><div className="min-w-0"><div ref={host} className="performance-canvas" style={{height:expanded?Math.max(560,innerHeight-230):540}}/>{!domain&&<p>No saved equity observations.</p>}</div>
 <aside className="performance-legend" aria-label="Run colour key"><p ref={hoverDate} className="text-xs muted">Hover either pane to inspect</p>{curves.map(curve=><div key={curve.id} className="performance-key" onMouseEnter={()=>setFocus(curve.id)} onMouseLeave={()=>setFocus(null)} onFocus={()=>setFocus(curve.id)} onBlur={()=>setFocus(null)}><button className="mini-btn" aria-pressed={!hidden.has(curve.id)} onClick={()=>setHidden(old=>{const next=new Set(old);next.has(curve.id)?next.delete(curve.id):next.add(curve.id);return next})}><span className="run-swatch" style={{background:styles.current.get(curve.id).color}}/>{curve.label}</button><button className="mini-btn" onClick={()=>setHidden(new Set(curves.filter(c=>c.id!==curve.id).map(c=>c.id)))}>Isolate</button><p className="text-xs" ref={el=>{if(el)legendRefs.current.set(curve.id,el);else legendRefs.current.delete(curve.id)}}>Hover to inspect</p></div>)}</aside></div>
 <p className="text-xs muted">Full history by default. Only exact unchanged plateau interiors are omitted; peaks, troughs, recovery transitions and trade events remain. A one-second initial balance anchor is shown when the first observation already changed equity.</p></section>;
}
