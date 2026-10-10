import {useEffect,useState,useRef} from 'react';
import {api} from '../../api/client';
const fields=[['description','Hypothesis'],['rationale','Economic rationale'],['feature','Feature or behavior'],['expected_result','Expected result'],['falsification','Falsification condition'],['researcher_reasoning','Researcher reasoning (your assessment)'],['devils_advocate_objections',"Devil?s Advocate objections (your assessment)"]];
export default function ResearchHypotheses({project,onTrialApproved}){
 const pending=useRef(null);
 const [items,setItems]=useState([]),[form,setForm]=useState({}),[datasets,setDatasets]=useState([]),[parameter,setParameter]=useState(''),[values,setValues]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const refresh=()=>api.researchHypotheses(project.id).then(r=>setItems(r.items));
 useEffect(()=>{refresh().catch(e=>setError(e.message));},[project.id]);
 const budget=project.research_budget||{max_hypotheses:12,max_variants_per_hypothesis:9,max_total_variants:60};
 const approve=async id=>{setBusy(true);setError('');try{await api.researchProjectAction(project.id,`hypotheses/${id}/approve`,{acknowledgement:'Run the frozen control and development variants'});onTrialApproved?.();}catch(e){setError(e.message);}finally{setBusy(false);}};
 const submit=async()=>{
  setBusy(true);setError('');
  try{
   const numbers=JSON.parse('['+values+']');
   if(!numbers.length||numbers.some(n=>typeof n!=='number'||!Number.isFinite(n)))throw Error('Use finite comma-separated numeric values.');
   const payload={...form,discovery_dataset_ids:datasets,axes:[{parameter,values:numbers}]};
   const signature=JSON.stringify(payload);
   if(pending.current?.signature!==signature)pending.current={signature,key:crypto.randomUUID()};
   await api.researchProjectAction(project.id,'hypotheses',{...payload,request_key:pending.current.key});
   await refresh();
  }catch(e){setError(e.message);}finally{setBusy(false);}
 };
 return <article className="insight-panel"><h4 className="font-semibold">Preregistered hypotheses</h4><p className="text-xs muted">User-authored or explicitly accepted committee proposals. Registration makes no model calls and starts no experiments. Each registration freezes the baseline and exact cells before future trials; it cannot be edited. Registration does not prove you have never tested these values elsewhere.</p>
 <p className="text-sm mt-2">Registered {items.length} / {budget.max_hypotheses} hypotheses ? {items.reduce((n,h)=>n+h.plan.job_count,0)} / {budget.max_total_variants} total variants ? at most {budget.max_variants_per_hypothesis} per hypothesis</p>
 {error&&<p role="alert">{error}</p>}
 {project.state==='BASELINE_ANALYSIS'&&project.baseline_run_id&&<details className="mt-3"><summary>Preregister a controlled parameter experiment</summary><div className="grid gap-3 mt-3 sm:grid-cols-2">{fields.map(([key,label])=><label key={key}>{label}<textarea className="input" value={form[key]||''} onChange={e=>setForm({...form,[key]:e.target.value})}/></label>)}<label>Declared numeric parameter<input className="input" value={parameter} onChange={e=>setParameter(e.target.value)}/></label><label>Exact values (comma-separated)<input className="input" value={values} onChange={e=>setValues(e.target.value)}/></label></div><fieldset className="mt-3"><legend>Data that informed this hypothesis</legend>{project.datasets.filter(d=>!['LOCKED_HOLDOUT','FUTURE_OOS'].includes(d.state)).map(d=><label className="block text-sm" key={d.id}><input type="checkbox" checked={datasets.includes(d.id)} onChange={e=>setDatasets(e.target.checked?[...datasets,d.id]:datasets.filter(id=>id!==d.id))}/> {d.symbols.join(', ')} / {d.start} ? {d.end} / {d.state}</label>)}</fieldset><button className="mini-btn mt-3" disabled={busy} onClick={submit}>{busy?'Registering?':'Preregister hypothesis'}</button></details>}
 {items.map(h=><details key={h.id} className="mt-3"><summary>{h.description} / {h.status} / {h.plan.job_count} variants</summary><p className="text-sm mt-2">Expected: {h.expected_result}</p><p className="text-sm">Falsified if: {h.falsification}</p><button className="mini-btn mt-2" disabled={busy||project.state!=='BASELINE_ANALYSIS'} onClick={()=>approve(h.id)}>Approve development trial</button><p className="text-xs muted">Runs a fresh control, then these {h.plan.job_count} frozen variants if parity passes. Existing approval is reused.</p><pre className="text-xs max-h-80 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify(h,null,2)}</pre></details>)}
 </article>;
}
