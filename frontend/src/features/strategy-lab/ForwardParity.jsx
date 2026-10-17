import {useState} from 'react';
import {api} from '../../api/client';
export default function ForwardParity({experiment,reports=[],onChecked}){
 const [date,setDate]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 async function run(){setBusy(true);setError('');try{await api.forwardParity(experiment,{session_date:date});await onChecked();}catch(e){setError(e.message);}finally{setBusy(false);}}
 return <details className="mt-3"><summary>Completed-session replay / parity</summary>
 <p className="text-xs muted mt-2">Replays the immutable prefix through the selected provider session close using fresh instances. This can take time. Live execution state is not changed. PASS verifies recorded shadow evidence, not broker-fill parity.</p>
 <label className="block mt-3">Completed session (New York date)<input className="input" type="date" value={date} onChange={e=>setDate(e.target.value)}/></label>
 <button className="mini-btn mt-2" disabled={busy||!date} onClick={run}>{busy?'Checking parity…':'Check session parity'}</button>
 {error&&<p role="alert">{error}</p>}
 {reports.map(r=><div key={r.session_date} className="mt-3"><strong>{r.session_date}: {r.status}</strong><p className="text-xs muted">Checked {r.checked_at}</p><ul>{r.results.map(d=><li key={d.deployment_id}>{d.name}: <strong>{d.status}</strong>{d.status==='FAIL'&&` — differing checks: ${Object.entries(d.checks).filter(([,ok])=>!ok).map(([k])=>k).join(', ')}`}</li>)}</ul></div>)}
 </details>;
}
