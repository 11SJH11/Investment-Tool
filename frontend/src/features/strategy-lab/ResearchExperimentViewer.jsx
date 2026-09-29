import {useEffect,useMemo,useState} from 'react';
import {api} from '../../api/client.js';
import {axisDisplay,cellDisplay,cellTooltip,experimentCells,experimentMetrics,heatScale,interactionAnalysis} from './researchExperiments.js';

const fmt=(v,d=2)=>v==null||!Number.isFinite(Number(v))?'—':Number(v).toFixed(d);

export default function ResearchExperimentViewer({experimentGroup,initial=null,jobs=[],onOpenRun,onBack,onError}) {
  const [data,setData]=useState(initial),[metric,setMetric]=useState('expectancy_r'),[view,setView]=useState('observed');
  const group=experimentGroup||data?.experiment_group;
  const parentJob=jobs.find(j=>j.payload?.experiment_group===group&&j.payload?.research_children);
  const stamp=parentJob?`${parentJob.status}:${parentJob.processed}:${parentJob.total}`:'';
  useEffect(()=>{
    if(!group)return;
    let live=true,timer;
    const load=async()=>{let status=parentJob?.status;try{const next=await api.strategyLabExperiment(group);status=next?.experiment?.status||status;if(live)setData(next);}catch(e){if(live)onError?.(e.message);}
      if(live&&!['completed','failed','cancelled'].includes(status))timer=setTimeout(load,1200);};
    load();return()=>{live=false;clearTimeout(timer);};
  // stamp intentionally refreshes when queue progress changes.
  },[group,stamp]);
  const doc=data?.experiment,plan=doc?.plan||data?.runs?.find(r=>r.config?.research_experiment)?.config?.research_experiment;
  const cells=useMemo(()=>experimentCells(plan,data?.runs||[],[],doc?.cells||[]),[plan,data?.runs,doc?.cells]);
  const relationship=useMemo(()=>interactionAnalysis(plan,cells,metric),[plan,cells,metric]);
  if(!group)return <section className="mt-5 rounded-xl border border-stone-200 bg-white p-5"><p>No research experiment selected.</p></section>;
  if(!plan)return <section className="mt-5 rounded-xl border border-stone-200 bg-white p-5"><div className="ui-toolbar"><button className="mini-btn" onClick={onBack}>← Runs</button><h2 className="font-semibold">Research experiment</h2></div><p className="mt-4 text-sm">Loading {group}…</p></section>;
  const completed=cells.filter(c=>c.status==='completed').length;
  const base=doc?.base_configuration||data?.runs?.[0]?.config||{};
  const metricLabel=experimentMetrics.find(([key])=>key===metric)?.[1]||metric;
  return <section className="mt-5 rounded-xl border border-stone-200 bg-white p-5 shadow-sm space-y-4 min-w-0">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><button className="mini-btn mb-3" onClick={onBack}>← Back to Runs</button><p className="text-xs uppercase tracking-wide text-stone-500">{plan.kind==='interaction'?'Interaction research':'Spectrum research'} · {(doc?.test_role||base?.test_role||'development').replaceAll('_',' ')}</p><h2 className="mt-1 text-xl font-semibold">{doc?.name||plan.name||'Research experiment'}</h2><p className="mt-1 text-xs text-stone-500">{base.strategy_key||'—'} · {(base.symbols||[]).join(', ')||'—'} · {base.start_date||'—'} → {base.end_date||'—'} · {base.primary_timeframe||'—'}</p></div><div className="text-right text-xs"><strong>{completed}/{cells.length} simulations</strong><div className="mt-1">{doc?.status||parentJob?.status||'saved'}</div></div></div>
    {doc?.notes&&<p className="rounded-lg bg-stone-50 p-3 text-sm">{doc.notes}</p>}
    <div className="ui-toolbar"><Field label="Result metric"><select className="input" value={metric} onChange={e=>setMetric(e.target.value)}>{experimentMetrics.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></Field>{plan.kind==='interaction'&&<Field label="Heatmap view"><select className="input" value={view} onChange={e=>setView(e.target.value)}><option value="observed">Observed metric</option><option value="interaction">Interaction residual</option></select></Field>}</div>
    <p className="text-xs text-stone-500">Every cell is an exact independent simulation. Low sample means N &lt; 30. Band axes use lower-inclusive, upper-exclusive intervals. Interaction residuals are descriptive only and do not select a winner.</p>
    {doc?.performance&&<details className="rounded-lg border border-stone-200 p-3"><summary className="cursor-pointer text-xs font-medium">Performance diagnostics · {doc.performance.workers??'—'} internal CPU workers</summary><pre className="mt-2 max-h-64 overflow-auto text-xs">{JSON.stringify(doc.performance,null,2)}</pre></details>}
    {plan.kind==='interaction'?<Heatmap plan={plan} cells={cells} metric={metric} relationship={relationship} mode={view} onOpen={onOpenRun}/>:<Spectrum plan={plan} cells={cells} metric={metric} onOpen={onOpenRun}/>} 
    {plan.kind==='interaction'&&relationship&&<RelationshipPanel analysis={relationship} metricLabel={metricLabel}/>} 
    <ResultTable plan={plan} cells={cells} onOpen={onOpenRun}/>
    <details className="rounded-lg border border-stone-200 p-3"><summary className="cursor-pointer text-xs font-medium">Exact experiment definition</summary><pre className="mt-2 max-h-80 overflow-auto text-xs">{JSON.stringify({axes:plan.axes,base_configuration:base,market_data_fingerprint:doc?.market_data_fingerprint},null,2)}</pre></details>
  </section>;
}

function ResultTable({plan,cells,onOpen}){return <div className="overflow-x-auto rounded-lg border border-stone-200"><table className="w-full min-w-[980px] text-xs"><thead><tr><th>Values / bands</th><th>Status</th><th>N</th><th>Average R</th><th>PF</th><th>Total R</th><th>Max DD R / %</th><th>Win %</th><th>Run</th></tr></thead><tbody>{cells.map(c=><tr key={c.index} title={cellTooltip(c,plan)}><td>{cellDisplay(plan,c.values)}{c.control?' · default control':''}</td><td>{c.status}{c.error?` · ${c.error}`:''}</td><td>{c.metrics?.trades??'—'}{c.lowN?' · Low sample':''}</td>{['expectancy_r','profit_factor_r','total_r'].map(k=><td key={k}>{fmt(c.metrics?.[k])}</td>)}<td>{fmt(c.metrics?.max_drawdown_r)} / {fmt(c.metrics?.max_drawdown_pct)}</td><td>{fmt(c.metrics?.win_rate_pct)}</td><td>{c.runId&&<button className="mini-btn" onClick={()=>onOpen?.(c.runId)}>Open #{c.runId}</button>}</td></tr>)}</tbody></table></div>}

function Heatmap({plan,cells,metric,relationship,mode,onOpen}){
  const residual=mode==='interaction';
  const value=c=>residual?relationship?.residuals?.get(c.index):c.metrics?.[metric];
  const scale=heatScale(cells,metric,value);
  const x=plan.axes[0],y=plan.axes[1];
  return <div className="overflow-x-auto"><p className="mb-2 text-xs">{residual?'Interaction residual':'Observed '+(experimentMetrics.find(([k])=>k===metric)?.[1]||metric)} · zero-centred scale −{fmt(scale)} to +{fmt(scale)}. X: {x.label}; Y: {y.label}.</p><table className="w-full text-xs"><thead><tr><th>Y \\ X</th>{x.values.map(v=><th key={v}>{axisDisplay(x,v)}</th>)}</tr></thead><tbody>{y.values.map(yv=><tr key={yv}><th>{axisDisplay(y,yv)}</th>{x.values.map(xv=>{const c=cells.find(q=>q.values[0]===xv&&q.values[1]===yv),v=c?value(c):null;return <td key={xv} className="p-1"><button className={`w-full min-w-24 rounded border p-3 ${c?.control?'ring-2 ring-blue-500':''}`} disabled={!c?.runId} title={c?cellTooltip(c,plan):''} onClick={()=>c?.runId&&onOpen?.(c.runId)} style={{backgroundColor:Number.isFinite(v)?`rgba(${v<0?'180,80,80':'60,140,120'},${.04+.28*Math.min(1,Math.abs(v)/scale)})`:'transparent'}}>{Number.isFinite(v)?fmt(v):c?.status||'—'}<span className="block">N {c?.metrics?.trades??'—'}{c?.lowN?' · Low sample':''}</span></button></td>})}</tr>)}</tbody></table></div>;
}
function Spectrum({plan,cells,metric,onOpen}){
  const points=cells.filter(c=>Number.isFinite(c.metrics?.[metric])).sort((a,b)=>a.values[0]-b.values[0]);
  if(!points.length)return <p className="text-sm">No completed numeric results yet.</p>;
  const axis=plan.axes[0],xs=axis.values,minX=Math.min(...xs),spanX=Math.max(1e-12,Math.max(...xs)-minX),scale=heatScale(cells,metric);
  const xy=c=>[55+680*(c.values[0]-minX)/spanX,140-110*c.metrics[metric]/scale];
  return <svg viewBox="0 0 800 290" className="w-full max-h-80" role="img" aria-label="Exact parameter spectrum results"><line x1="50" y1="140" x2="755" y2="140" stroke="currentColor" opacity=".3"/><text x="5" y="35" fontSize="12">{fmt(scale)}</text><text x="5" y="145" fontSize="12">0</text><text x="5" y="255" fontSize="12">−{fmt(scale)}</text><polyline points={points.map(c=>xy(c).join(',')).join(' ')} fill="none" stroke="currentColor" opacity=".4"/>{points.map(c=>{const [px,py]=xy(c);return <g key={c.index} role="button" tabIndex="0" aria-label={cellTooltip(c,plan)} onClick={()=>c.runId&&onOpen?.(c.runId)} onKeyDown={e=>{if((e.key==='Enter'||e.key===' ')&&c.runId){e.preventDefault();onOpen?.(c.runId);}}}><title>{cellTooltip(c,plan)}</title><circle cx={px} cy={py} r={c.control?7:5} fill={c.lowN?'transparent':'currentColor'} stroke="currentColor" strokeWidth={c.control?3:1}/><text x={px} y="280" textAnchor="middle" fontSize="11">{axisDisplay(axis,c.values[0])}</text></g>})}</svg>;
}
function RelationshipPanel({analysis,metricLabel}){const Table=({title,rows})=><div><h4 className="text-sm font-semibold">{title}</h4><table className="mt-2 w-full text-xs"><thead><tr><th>Value / band</th><th>Mean {metricLabel}</th><th>Δ vs grid mean</th><th>Cells</th><th>Combined N</th></tr></thead><tbody>{rows.map(r=><tr key={String(r.value)}><td>{r.label}</td><td>{fmt(r.mean)}</td><td>{Number.isFinite(r.effect)?`${r.effect>=0?'+':''}${fmt(r.effect)}`:'—'}</td><td>{r.cells}</td><td>{r.trades}</td></tr>)}</tbody></table></div>;return <section className="rounded-lg border border-stone-200 bg-stone-50 p-4"><div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="text-sm font-semibold">Interaction relationship analysis</h3><p className="mt-1 text-xs text-stone-500">Marginal means show each axis averaged across the other axis. Δ compares that marginal with the grid-wide mean. The residual heatmap isolates cells above/below an additive X + Y pattern.</p></div><div className="text-xs text-stone-500">Grid mean: <strong>{fmt(analysis.grand)}</strong></div></div><div className="mt-3 grid gap-4 lg:grid-cols-2"><Table title="X marginal relationship" rows={analysis.xMarginals}/><Table title="Y marginal relationship" rows={analysis.yMarginals}/></div><p className="mt-3 text-xs text-amber-800">{analysis.note}</p></section>}
function Field({label,children}){return <label className="block text-xs"><span className="mb-1 block">{label}</span>{children}</label>}
