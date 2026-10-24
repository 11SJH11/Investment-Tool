import DataTable from '../../components/table/DataTable';
import {useState} from 'react';
import DiagnosticDecisions from './DiagnosticDecisions';

const columns=[
 {key:'profile_id',label:'Demo profile',kind:'text'},
 {key:'state',label:'Observed worker state',kind:'category'},
 {key:'thread_alive',label:'Thread in this backend',kind:'category',render:row=>row.thread_alive?'Alive':'Not observed'},
 {key:'heartbeat_at',label:'Last heartbeat',kind:'date'},
 {key:'last_decision_at',label:'Last completed decision',kind:'date'},
 {key:'error_category',label:'Last error',kind:'category',render:row=>row.error_category?.replaceAll('_',' ')??'None'},
 {key:'stream_id',label:'Diagnostic stream',kind:'text'},
];

export default function DiagnosticWorkers({rows=[]}){
 const [selected,setSelected]=useState(null);
 return <article className="insight-panel" aria-label="Read-only diagnostic workers">
  <h2 className="font-semibold">Diagnostic workers</h2>
  <p className="text-xs muted">Read-only T01 observation workers, not trading deployments. A live thread is not proof of fresh market data. Stalled or interrupted workers require inspection; Ledger never resumes them automatically after restart.</p>
  {rows.length?<DataTable id="algo.diagnosticWorkers" label="Diagnostic worker health" columns={columns} rows={rows} primaryAction={{label:'View decisions',onClick:row=>setSelected(row.stream_id)}}/>:<p className="text-sm mt-2">No diagnostic worker has been explicitly started.</p>}
  {selected&&<><button className="mini-btn mt-3" onClick={()=>setSelected(null)}>Close decisions</button><DiagnosticDecisions key={selected} streamId={selected}/></>}
  <p className="text-xs muted mt-2">Stopping diagnostics does not close positions or provide position protection. Automated execution remains disabled.</p>
 </article>;
}
