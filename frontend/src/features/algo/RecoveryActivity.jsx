import {useEffect,useRef,useState} from 'react';
import {api} from '../../api/client';
import DataTable from '../../components/table/DataTable';

const columns=[
 {key:'observed_at_ms',label:'Observed at',kind:'date',render:row=>row.observed_at_ms?new Date(row.observed_at_ms).toLocaleString():'Unavailable'},
 {key:'state',label:'Recorded recovery state',kind:'category'},
 {key:'identity_basis',label:'Identity evidence',kind:'category'},
 {key:'complete',label:'Complete observation',kind:'category',render:row=>row.complete?'Yes':'No'},
 {key:'filled_lots',label:'Filled lots',kind:'number'},
 {key:'remaining_lots',label:'Remaining lots',kind:'number'},
 {key:'intent_id',label:'Intent',kind:'text'}];

export default function RecoveryActivity({policyId}){
 const [page,setPage]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[older,setOlder]=useState(false);
 const generation=useRef(0),pending=useRef(false);
 const load=async before=>{
  if(pending.current)return;
  pending.current=true;setBusy(true);setError('');const id=++generation.current;
  try{const next=await api.algoRecovery(policyId,before);if(id===generation.current){setPage(next);setOlder(before!=null);}}
  catch(e){if(id===generation.current)setError(e.message);}
  finally{if(id===generation.current){pending.current=false;setBusy(false);}}
 };
 useEffect(()=>{load(null);return()=>{generation.current++;pending.current=false;};},[]);
 return <article className="insight-panel" aria-label="MT5 recovery observations">
  <h2 className="font-semibold">MT5 recovery observations</h2>
  <p className="text-xs muted">Paged persisted observations{policyId?' for the selected preparation':''}, not a live position snapshot. Protection evidence may be stale. These observations do not release account guards, verify strategy attribution or authorize trading.</p>
  {error&&<p role="alert">{error}. {page?'Previous page retained.':'No recovery page received.'}</p>}
  {busy&&<p role="status">Loading recovery observations…</p>}
  <DataTable id="algo.recovery" label="MT5 recovery evidence" columns={columns} rows={page?.items||[]}/>
  <div className="ui-toolbar mt-3">
   <button className="mini-btn" disabled={busy} onClick={()=>load(null)}>{older?'Latest recovery observations':'Refresh recovery observations'}</button>
   {page?.next_before!=null&&<button className="mini-btn" disabled={busy} onClick={()=>load(page.next_before)}>Older recovery observations</button>}
  </div>
 </article>;
}
