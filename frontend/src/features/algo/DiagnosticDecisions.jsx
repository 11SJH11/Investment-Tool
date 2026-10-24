import {useEffect,useState} from 'react';
import {api} from '../../api/client';
import DataTable from '../../components/table/DataTable';

const columns=[
 {key:'sequence',label:'Sequence',kind:'number'},
 {key:'decision_at',label:'Completed bar decision',kind:'date'},
 {key:'decision_kind',label:'Recorded decision',kind:'category'},
 {key:'direction',label:'Direction',kind:'category'},
 {key:'stop_loss',label:'Suggested initial stop',kind:'number'},
 {key:'target_r',label:'Suggested target R',kind:'number'},
 {key:'new_stop_loss',label:'Suggested managed stop',kind:'number'},
 {key:'not_before',label:'Earliest eligible application',kind:'date'},
 {key:'integrity',label:'Stored evidence integrity',kind:'category'},
];

export default function DiagnosticDecisions({streamId}){
 const [request,setRequest]=useState({before:null}),[page,setPage]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(true);
 useEffect(()=>{let current=true;setBusy(true);setError('');
  api.algoDecisions(streamId,request.before).then(next=>{if(current)setPage(next);})
   .catch(e=>{if(current)setError(e.message);}).finally(()=>{if(current)setBusy(false);});
  return()=>{current=false;};
 },[streamId,request]);
 return <article className="insight-panel" aria-label="Recorded diagnostic decisions">
  <h3 className="font-semibold">Recorded diagnostic decisions</h3>
  <p className="text-xs muted">Persisted observations only. Entry and management suggestions are not orders, fills, current positions or proof of protection. No signal means the strategy returned no action; a more specific reason was not recorded. Filters apply to the loaded page.</p>
  {error&&<p role="alert">{error}. {page?'Previous decisions retained.':'No decisions received.'}</p>}
  {busy&&<p role="status">Loading decisions…</p>}
  <DataTable id="algo.diagnosticDecisions" label="Diagnostic decision evidence" columns={columns} rows={page?.items??[]}/>
  <div className="ui-toolbar mt-3">
   <button className="mini-btn" disabled={busy} onClick={()=>setRequest({before:null})}>Latest diagnostic decisions</button>
   {page?.next_before!=null&&<button className="mini-btn" disabled={busy} onClick={()=>setRequest({before:page.next_before})}>Older diagnostic decisions</button>}
  </div>
 </article>;
}
