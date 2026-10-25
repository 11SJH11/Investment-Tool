import {useEffect,useRef,useState} from 'react';
import {api} from '../../api/client';
import {emitDiagnostics} from './researchDiagnostics.js';

export default function ResearchEventStream({identifier,report}){
 const [draft,setDraft]=useState(''),[token,setToken]=useState(''),[events,setEvents]=useState([]);
 const [error,setError]=useState(''),[debug,setDebug]=useState(false),[notice,setNotice]=useState('');
 const cursor=useRef(0),seen=useRef(new Set());
 useEffect(()=>{
  if(!token)return;
  const controller=new AbortController();
  api.researchDiagnostics(identifier,cursor.current,token,controller.signal).then(page=>{
   if(controller.signal.aborted)return;
   cursor.current=page.next_after;
   setEvents(current=>[...new Map([...current,...page.items].map(event=>[event.event_id,event])).values()].slice(-200));
   setError('');setNotice(page.retention_gap?'Earlier events may have expired from bounded retention.':page.has_more?'More events will load on the next normal campaign refresh.':'');
  }).catch(e=>{if(!controller.signal.aborted)setError(e.message);});
  return()=>controller.abort();
 },[identifier,report,token]);
 useEffect(()=>{if(debug)emitDiagnostics(events,seen.current);},[events,debug]);
 const connect=()=>{cursor.current=0;seen.current.clear();setEvents([]);setToken(draft);setDraft('');};
 const disconnect=()=>{setToken('');setDraft('');setEvents([]);setError('');setNotice('');setDebug(false);};
 const copy=async()=>{try{await navigator.clipboard.writeText(JSON.stringify({campaign_id:identifier,events},null,2));setNotice('Safe event report copied');}catch{setError('Clipboard unavailable. Expand and select event details.');}};
 return <details className="insight-panel"><summary>Research lifecycle diagnostics</summary>
  <p className="text-xs muted">Authenticated local diagnostics. Token stays in memory until disconnected or page reload. This does not secure other Ledger routes.</p>
  {!token?<div><label>Diagnostic access token<input className="input" type="password" autoComplete="off" value={draft} onChange={e=>setDraft(e.target.value)}/></label><button className="mini-btn" disabled={draft.length<32} onClick={connect}>Connect diagnostics</button></div>:<button className="mini-btn" onClick={disconnect}>Disconnect diagnostics</button>}
  {import.meta.env.DEV&&<label><input type="checkbox" checked={debug} onChange={e=>setDebug(e.target.checked)}/> Log events to F12 console</label>}
  {!!events.length&&<button className="mini-btn" onClick={copy}>Copy event diagnostics</button>}
  {error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
  {token&&!error&&!events.length&&<p className="text-xs muted">No lifecycle events received yet. Earlier failures remain in the existing diagnostics panel; old events are not fabricated.</p>}
  <div className="max-h-96 overflow-auto">{events.slice().reverse().map(event=><details key={event.event_id}><summary>{event.timestamp} · {event.component} · {event.operation} · {event.status}</summary><pre className="text-xs whitespace-pre-wrap break-all">{JSON.stringify(event,null,2)}</pre></details>)}</div>
 </details>;
}
