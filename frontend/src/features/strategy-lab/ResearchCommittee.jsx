import {useEffect,useState,useRef} from 'react';
import {api} from '../../api/client';
const CONSENT='Send development summaries to the configured model';
export default function ResearchCommittee({project,onPreregister}){
 const [status,setStatus]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[consent,setConsent]=useState(false);
 const requestKey=useRef(null);
 const refresh=()=>api.researchCommittee(project.id).then(setStatus);
 useEffect(()=>{let alive=true;let timer;const poll=async()=>{try{const r=await api.researchCommittee(project.id);if(!alive)return;setStatus(r);if(r.items.some(x=>x.status==='RUNNING'))timer=setTimeout(poll,2500);}catch(e){if(alive)setError(e.message);}};poll();return()=>{alive=false;clearTimeout(timer);};},[project.id,busy]);
 const start=async()=>{
  setBusy(true);setError('');requestKey.current ||= crypto.randomUUID();
  try{await api.researchProjectAction(project.id,'committee',{request_key:requestKey.current,consent:CONSENT});requestKey.current=null;await refresh();}
  catch(e){setError(e.message);}finally{setBusy(false);}
 };
 const register=async id=>{setBusy(true);setError('');try{await api.researchProjectAction(project.id,`committee/${id}/preregister`,{});onPreregister();await refresh();}catch(e){setError(e.message);}finally{setBusy(false);}};
 const running=status?.items.some(r=>r.status==='RUNNING');
 return <article className="insight-panel"><h4 className="font-semibold">Read-only research committee</h4>
 <p className="text-sm muted mt-2">Researcher proposes; Devil's Advocate challenges; Manager recommends, revises or rejects. Recommendations never launch backtests or change strategies.</p>
 <p className="text-xs mt-2">{status?.model.configured?`OpenAI / ${status.model.model}`:'Not configured: set RESEARCH_LLM_ENABLED, RESEARCH_LLM_API_KEY and RESEARCH_LLM_MODEL on the backend.'} Calls reserved: {status?.reserved_calls??0} / {status?.max_calls??'Unavailable'}.</p>
 <p className="text-xs muted">Each review reserves up to three paid API calls, including failed/interrupted attempts. No automatic retries. Priced projects reserve the maximum call allowance before sending. Failed/interrupted calls retain the reservation. Quotes are configured on the backend, not live billing rates.</p>
 <p className="text-xs muted">Reserved estimate: ${status?.reserved_cost_usd??0} / {status?.max_spend_usd==null?"No monetary cap (legacy manual project)":`$${status.max_spend_usd}`}.</p>
 {error&&<p role="alert">{error}</p>}
 <label className="block text-sm mt-3"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/> I agree to send the baseline and completed trials' development summaries, numeric parameters and strategy description to the configured model. No journal/broker data, notes or raw strategy source.</label>
 <button className="mini-btn mt-2" disabled={busy||running||!consent||!status?.model.configured||project.state!=='BASELINE_ANALYSIS'||status.max_calls-status.reserved_calls<3} onClick={start}>{busy?'Reviewing...':'Run committee review'}</button>
 {status?.items.map(r=><details className="mt-3" key={r.id} open={r.status==='RUNNING'}><summary>{r.created_at} / {r.status}{r.roles.Manager?' / '+r.roles.Manager.decision:''}</summary>{r.error&&<p role="alert" className="text-sm">{r.error}</p>}{Object.entries(r.roles).map(([role,result])=><section key={role} className="mt-3"><h5 className="font-semibold">{role}</h5><p className="text-xs muted">Model-generated interpretation; cited evidence does not establish causality.</p><pre className="text-xs overflow-auto whitespace-pre-wrap break-all">{JSON.stringify(result,null,2)}</pre></section>)}{r.status==='COMPLETED'&&r.roles.Manager?.decision==='RECOMMEND_EXPERIMENT'&&<button className="mini-btn mt-3" disabled={busy||project.state!=='BASELINE_ANALYSIS'} onClick={()=>register(r.id)}>Preregister recommendation</button>}<details className="mt-3"><summary>Evidence snapshot and token usage</summary><pre className="text-xs max-h-80 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify({evidence:r.evidence,evidence_hash:r.evidence_hash,usage:r.usage,provider:r.provider},null,2)}</pre></details></details>)}
 </article>;
}
