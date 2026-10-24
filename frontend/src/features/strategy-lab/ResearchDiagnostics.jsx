import {useEffect,useRef,useState} from 'react';
import {emitDiagnostics} from './researchDiagnostics';

export default function ResearchDiagnostics({operations}){
 const [debug,setDebug]=useState(false),[notice,setNotice]=useState('');
 const seen=useRef(new Set());
 const events=(operations||[]).map(op=>op.diagnostic).filter(Boolean);
 useEffect(()=>{if(debug)emitDiagnostics(events,seen.current);},[debug,events]);
 if(!events.length)return null;
 const copy=async()=>{try{await navigator.clipboard.writeText(JSON.stringify({version:1,events},null,2));setNotice('Diagnostics copied');}catch{setNotice('Clipboard unavailable; expand and select the diagnostic text.');}};
 return <article className="insight-panel" aria-label="Research diagnostics">
  <h4 className="font-semibold">Research diagnostics</h4>
  <p className="text-xs muted">Persisted model-validation failures. Other stages are not yet covered by this panel. No automatic retry.</p>
  {import.meta.env.DEV&&<label><input type="checkbox" checked={debug} onChange={e=>setDebug(e.target.checked)}/> Log diagnostics to F12 console</label>}
  <button className="mini-btn" onClick={copy}>Copy diagnostics</button>
  {notice&&<p role="status">{notice}</p>}
  {events.map(event=><details key={event.event_id} className="mt-3">
   <summary>{event.timestamp} · {event.error_code}</summary>
   <p>{event.message}</p><p>{event.suggested_action}</p>
   {event.legacy_details_unavailable&&<p>Legacy record: the rejected reference was not retained.</p>}
   <pre className="text-xs whitespace-pre-wrap break-all">{JSON.stringify(event,null,2)}</pre>
  </details>)}
 </article>;
}
