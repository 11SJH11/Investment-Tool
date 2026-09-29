import {useEffect,useMemo,useRef,useState} from 'react';
import {api} from '../../api/client';

const initialAxis=p=>({parameter:p?.key||'',mode:'explicit',values:String(p?.default??''),start:String(p?.default??0),end:String(p?.default??0),step:String(p?.step||1),spacing:'step',count:'5',bandSource:'explicit'});
const axisRequest=a=>{
  if(a.mode==='explicit')return {parameter:a.parameter,mode:'explicit',values:a.values};
  if(a.mode==='bands'&&a.bandSource==='explicit')return {parameter:a.parameter,mode:'bands',values:a.values};
  return {parameter:a.parameter,mode:a.mode,start:a.start,end:a.end,[a.spacing]:a[a.spacing]};
};

export default function ResearchExperimentPanel({strategy,buildPayload,refresh,onError,onOpenExperiment}) {
  const parameters=useMemo(()=>[...(strategy?.parameters||[]),...(strategy?.research_parameters||[])].filter(p=>['int','float'].includes(p.kind)),[strategy]);
  const [kind,setKind]=useState('spectrum'),[axes,setAxes]=useState([initialAxis(parameters[0]),initialAxis(parameters[1])]);
  const [name,setName]=useState('Parameter research'),[notes,setNotes]=useState(''),[tags,setTags]=useState(''),[role,setRole]=useState('development');
  const [preview,setPreview]=useState(null),[busy,setBusy]=useState(false),[workers,setWorkers]=useState('global'),[last,setLast]=useState(null);
  const pending=useRef(null);
  useEffect(()=>{setAxes([initialAxis(parameters[0]),initialAxis(parameters[1])]);setPreview(null);},[strategy?.key]);
  const base=buildPayload(),axisPayload=axes.slice(0,kind==='spectrum'?1:2).map(axisRequest);
  const signature=JSON.stringify({base,axes:axisPayload,name,notes,tags,role,workers});
  useEffect(()=>setPreview(null),[signature]);
  const request=()=>{if(pending.current?.signature!==signature)pending.current={signature,key:crypto.randomUUID()};return {...JSON.parse(signature),tags:tags.split(',').map(t=>t.trim()).filter(Boolean),request_key:pending.current.key};};
  const verify=async()=>{setBusy(true);try{const payload=request(),result=await api.previewResearchExperiment(payload);setPreview({plan:result,payload,signature});}catch(e){onError?.(e.message);}finally{setBusy(false);}};
  const submit=async()=>{if(preview?.signature!==signature)return;setBusy(true);try{const result=await api.submitResearchExperiment(preview.payload);pending.current=null;setPreview(null);setLast({group:result.experiment_group,count:result.job_count});await refresh?.();onOpenExperiment?.(result.experiment_group);}catch(e){onError?.(e.message);}finally{setBusy(false);}};
  const changeAxis=(i,next)=>setAxes(old=>old.map((a,j)=>j===i?next:a));
  return <section className="p-4 space-y-4 min-w-0">
    <p className="text-sm">Configure exact parameter research here. Completed/running experiment results open in the dedicated Research Viewer and remain persisted under Runs → Research experiments.</p>
    <div className="ui-toolbar"><label>Research mode <select className="input" value={kind} onChange={e=>setKind(e.target.value)}><option value="spectrum">1D sensitivity / spectrum</option><option value="interaction">2D interaction grid</option></select></label></div>
    {axes.slice(0,kind==='spectrum'?1:2).map((a,i)=>{const p=parameters.find(q=>q.key===a.parameter);return <fieldset key={i} className="border rounded p-3"><legend>Parameter {i?'Y':'X'}</legend><div className="grid gap-3 sm:grid-cols-3">
      <Field label="Parameter"><select className="input" value={a.parameter} onChange={e=>changeAxis(i,initialAxis(parameters.find(p=>p.key===e.target.value)))}>{parameters.map(p=><option key={p.key} value={p.key}>{p.label}</option>)}</select></Field>
      <Field label="Values mode"><select className="input" value={a.mode} onChange={e=>changeAxis(i,{...a,mode:e.target.value,bandSource:e.target.value==='bands'?'explicit':a.bandSource})}><option value="explicit">Explicit values</option><option value="range">Range / spectrum</option>{p?.paired_max_key&&<option value="bands">Non-overlapping bands [min,max)</option>}</select></Field>
      {a.mode==='explicit'&&<Field label="Comma-separated values"><input className="input" value={a.values} onChange={e=>changeAxis(i,{...a,values:e.target.value})}/></Field>}
      {a.mode==='bands'&&<><Field label="Band edge source"><select className="input" value={a.bandSource} onChange={e=>changeAxis(i,{...a,bandSource:e.target.value})}><option value="explicit">Explicit edges</option><option value="range">Generated edges</option></select></Field>{a.bandSource==='explicit'?<Field label="Comma-separated edges"><input className="input" value={a.values} placeholder="1, 1.25, 1.5, 1.75, 2" onChange={e=>changeAxis(i,{...a,values:e.target.value})}/></Field>:<RangeFields axis={a} set={next=>changeAxis(i,next)} bands/>}</>}
      {a.mode==='range'&&<RangeFields axis={a} set={next=>changeAxis(i,next)}/>} 
    </div><p className="text-xs mt-2">Declared default: {p?.default}. {a.mode==='bands'?`Each interval sets ${p?.key} to its lower edge and ${p?.paired_max_key} to its exclusive upper edge; every band is rerun exactly.`:'Include the default to show a control point.'} Limit: {kind==='spectrum'?25:8} {a.mode==='bands'?'bands':'values'} per axis.</p></fieldset>})}
    <div className="grid gap-3 sm:grid-cols-2"><Field label="Experiment name"><input className="input" value={name} onChange={e=>setName(e.target.value)}/></Field><Field label="Role"><select className="input" value={role} onChange={e=>setRole(e.target.value)}>{['development','validation','out_of_sample'].map(v=><option key={v} value={v}>{v.replaceAll('_',' ')}</option>)}</select></Field><Field label="Notes"><input className="input" value={notes} onChange={e=>setNotes(e.target.value)}/></Field><Field label="Tags"><input className="input" value={tags} onChange={e=>setTags(e.target.value)}/></Field></div>
    <div className="ui-toolbar"><Field label="Compute workers"><select className="input" value={workers} onChange={e=>setWorkers(e.target.value)}><option value="global">Use global Backtest setting</option><option value="auto_conservative">Auto · conservative</option><option value="auto_performance">Auto · performance</option>{['1','2','4','6','8'].map(n=><option key={n} value={n}>{n}</option>)}</select></Field><button className="mini-btn" disabled={busy||!parameters.length} onClick={verify}>Preview exact values</button></div>
    <p className="text-xs">One parent queue job; independent exact simulations inside it. Start coarse (3×3 = 9) and refine only interesting regions. Multiple workers accelerate independent cells, not the causal loop inside one simulation.</p>
    {preview?.signature===signature&&<div className="p-3 border rounded" role="status">{preview.plan.axes.map(a=><p key={a.parameter}>{a.label}: {a.labels.join(', ')}{a.mode==='bands'?' [lower, upper)':''}</p>)}<strong>{preview.plan.job_count} exact backtests will be run.</strong> <button className="mini-btn" disabled={busy} onClick={submit}>Queue experiment</button></div>}
    {last&&<div className="rounded-lg border border-stone-200 bg-stone-50 p-3 text-sm">Research queued as one parent job ({last.count} simulations). <button className="mini-btn ml-2" onClick={()=>onOpenExperiment?.(last.group)}>Open Research Viewer</button></div>}
  </section>;
}
function RangeFields({axis,set,bands=false}){return <><Field label="Spacing"><select className="input" value={axis.spacing} onChange={e=>set({...axis,spacing:e.target.value})}><option value="step">{bands?'Band width':'Step'}</option><option value="count">{bands?'Number of bands':'Number of values'}</option></select></Field>{['start','end',axis.spacing].map(k=><Field key={k} label={k==='count'?(bands?'bands':'count'):k}><input className="input" inputMode="decimal" value={axis[k]} onChange={e=>set({...axis,[k]:e.target.value})}/></Field>)}</>}
function Field({label,children}){return <label className="block text-xs"><span className="block mb-1">{label}</span>{children}</label>}
