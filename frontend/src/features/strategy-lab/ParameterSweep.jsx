import {sweepAxes} from './parameterSweeps.js';
export {sweepAxes} from './parameterSweeps.js';
import {useEffect,useRef,useState} from 'react';
import {api} from '../../api/client.js';
import {notifyActivity} from '../../app/activityEvents.js';
export function SweepField({parameter,sweep,onChange,children}){
 if(!['int','float'].includes(parameter.kind))return children;
 const value=sweep||{mode:'fixed',values:String(parameter.default),start:String(parameter.default),end:String(parameter.default),step:String(parameter.step||1)};
 return <div>{children}<label className="text-xs">Parameter mode <select className="input" aria-label={`${parameter.label} mode`} value={value.mode} onChange={e=>onChange({...value,mode:e.target.value})}><option value="fixed">Fixed value</option><option value="explicit">Multiple values</option><option value="range">Range</option></select></label>
 {value.mode==='explicit'&&<label className="text-xs">Comma-separated values<input className="input" value={value.values} onChange={e=>onChange({...value,values:e.target.value})}/></label>}
 {value.mode==='range'&&<div className="grid grid-cols-3 gap-2">{['start','end','step'].map(key=><label className="text-xs" key={key}>{key}<input className="input" inputMode="decimal" value={value[key]} onChange={e=>onChange({...value,[key]:e.target.value})}/></label>)}</div>}</div>;
}

export default function IntegratedResearch({base,sweeps,refresh}){
 const axes=sweepAxes(sweeps),signature=JSON.stringify({base,axes});
 const [preview,setPreview]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 const pending=useRef(null);
 useEffect(()=>{setPreview(null);setError('');setMessage('');let stale=false;
 const timer=setTimeout(async()=>{try{
 if(axes.length>2)throw Error('At most two varied parameters are supported by the existing research engine. Keep other parameters fixed.');
 if(!base.symbols.length)throw Error('Select at least one symbol.');
 const plans=await Promise.all(base.symbols.map(symbol=>api.previewResearchExperiment({base:{...base,symbols:[symbol]},axes,name:base.run_name||'Parameter research'})));
 if(!stale)setPreview({signature,plans,total:plans.reduce((n,p)=>n+p.job_count,0)});
 }catch(e){if(!stale)setError(e.message)}},350);
 return()=>{stale=true;clearTimeout(timer)};
 },[signature]);
 const submit=async()=>{if(!preview||preview.signature!==signature)return;setBusy(true);setError('');
 if(pending.current?.signature!==signature)pending.current={signature,keys:base.symbols.map(()=>crypto.randomUUID()),done:new Set()};
 try{for(let i=0;i<base.symbols.length;i++){
 if(pending.current.done.has(i))continue;
 const symbol=base.symbols[i];await api.submitResearchExperiment({base:{...base,symbols:[symbol]},axes,name:`${base.run_name||'Parameter research'} / ${symbol}`,role:base.test_role,notes:base.run_notes,tags:base.run_tags,workers:'global',request_key:pending.current.keys[i]});pending.current.done.add(i);
 }notifyActivity({title:'Research queued',detail:`${preview.total} tests across ${base.symbols.length} symbol(s). Independent capital per symbol.`});setMessage('Queued. Follow progress in Activity; open completed results there.');await refresh?.();
 }catch(e){setError(`${pending.current.done.size} symbol experiment(s) queued. Retry safely: ${e.message}`)}finally{setBusy(false)}};
 return <div className="ui-section" aria-label="Integrated parameter research"><h4>Parameter research</h4>{!preview&&!error&&<p role="status">Calculating exact experiment size...</p>}{error&&<p role="alert">{error}</p>}{preview?.signature===signature&&<><p>{preview.plans[0].job_count} parameter combinations ? {base.symbols.length} symbols = <strong>{preview.total} backtests</strong></p><p className="text-xs">Independent simulations, not a combined portfolio. Existing per-axis research limits apply.</p>{preview.total>50&&<p role="status">Large experiment: {preview.total} complete simulations may take significant time.</p>}<button className="mini-btn" disabled={busy||!!message} onClick={submit}>{busy?'Queueing research...':`Run ${preview.total} tests`}</button></>}{message&&<p role="status">{message}</p>}</div>;
}
