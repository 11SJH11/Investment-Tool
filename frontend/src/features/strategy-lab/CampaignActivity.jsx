import {useEffect,useRef,useState} from 'react';
import {api} from '../../api/client';

export default function CampaignActivity({identifier,page}){
 const [older,setOlder]=useState([]),[cursor,setCursor]=useState(null),[loaded,setLoaded]=useState(false);
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const alive=useRef(true);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 if(!page)return null;
 const next=loaded?cursor:page.next_before;
 const items=loaded?older:page.items;
 const load=async()=>{
  setBusy(true);setError('');
  try{const result=await api.researchCampaignActivity(identifier,next);if(!alive.current)return;
   setOlder(result.items);setCursor(result.next_before);setLoaded(true);
  }catch(e){if(alive.current)setError(e.message);}finally{if(alive.current)setBusy(false);}
 };
 return <article className="insight-panel" aria-label="Campaign activity">
  <h4 className="font-semibold">Persisted activity</h4>
  <p className="text-xs muted">Newest first. Recorded campaign events, not a worker heartbeat.</p>
  {!items.length&&<p>No recorded events.</p>}
  <div className="max-h-96 overflow-auto mt-3">{items.map(item=><details key={item.id} className="py-2">
   <summary className="text-sm break-words">{item.created_at} · {item.action.replaceAll('_',' ')}</summary>
   <pre className="text-xs whitespace-pre-wrap break-all">{item.detail}</pre>
  </details>)}</div>
  {error&&<p role="alert">{error}</p>}
  {loaded&&<button className="mini-btn mt-3" disabled={busy} onClick={()=>{setLoaded(false);setOlder([]);setError('');}}>Latest activity</button>}
  {next!=null&&<button className="mini-btn mt-3" disabled={busy} onClick={load}>{busy?'Loading…':'Load older activity'}</button>}
 </article>;
}
