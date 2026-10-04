import {useEffect,useRef,useState} from 'react';
import useBacktestJobs from '../features/strategy-lab/useBacktestJobs.js';
import BacktestJobPanel from '../features/strategy-lab/BacktestJobPanel.jsx';
import {jobTransitions,jobDestination,notifyActivity,subscribeActivity,subscribeBusy} from './activityEvents.js';
import {activeStatus} from '../features/strategy-lab/statusPolling.js';
const storageKey='ledger.activity.history.v1';
function history(){try{return JSON.parse(localStorage.getItem(storageKey)||'[]').slice(0,100)}catch{return []}}
export default function ActivityCentre({onOpen}){
 const [busy,setBusy]=useState([]);useEffect(()=>subscribeBusy(setBusy),[]);
 const queue=useBacktestJobs();const previous=useRef(new Map());
 const [open,setOpen]=useState(false),[events,setEvents]=useState(history),[toasts,setToasts]=useState([]);
 useEffect(()=>subscribeActivity(event=>{setEvents(old=>[event,...old.filter(e=>e.id!==event.id)].slice(0,100));setToasts(old=>[...old,event].slice(-4));}),[]);
 useEffect(()=>{try{localStorage.setItem(storageKey,JSON.stringify(events))}catch{}},[events]);
 useEffect(()=>{if(!toasts.length)return;const timer=setTimeout(()=>setToasts(old=>old.slice(1)),8000);return()=>clearTimeout(timer)},[toasts]);
 useEffect(()=>{
  for(const job of jobTransitions(previous.current,queue.jobs))notifyActivity({id:`job-${job.id}-${job.status}`,title:`${job.payload?.experiment_group?'Research':'Backtest'} ${job.status}`,detail:job.payload?.run_name||job.payload?.strategy_key,destination:jobDestination(job)});
  previous.current=new Map(queue.jobs.map(j=>[j.id,j.status]));
 },[queue.jobs]);
 const navigate=destination=>{setOpen(false);onOpen(destination)};
 const active=queue.jobs.filter(j=>activeStatus(j.status)).length;
 return <>{busy.length>0&&<span className="text-xs muted" role="status">{busy[0]}...</span>}<button className="mini-btn" aria-expanded={open} aria-controls="ledger-activity" onClick={()=>setOpen(!open)}>Activity{active?` (${active})`:''}</button>
 {open&&<aside id="ledger-activity" aria-label="Activity centre" className="activity-centre"><div className="ui-toolbar"><h2>Activity</h2><button className="mini-btn" onClick={()=>setOpen(false)}>Close activity</button></div>
 <BacktestJobPanel queue={queue} onOpen={runId=>navigate({runId})} onOpenExperiment={experimentGroup=>navigate({experimentGroup})}/>
 <h3>Recent notifications</h3>{events.map(event=><article key={event.id} className="ui-section"><strong>{event.title}</strong><p>{event.detail}</p><small>{new Date(event.created_at).toLocaleString()}</small>{event.destination&&<button className="mini-btn" onClick={()=>navigate(event.destination)}>Open results</button>}</article>)}
 {!events.length&&<p>No notifications yet.</p>}<button className="mini-btn" onClick={()=>setEvents([])}>Clear notification history</button></aside>}
 <div className="activity-toasts" aria-live="polite">{toasts.map(event=><div key={event.id} className="activity-toast"><strong>{event.title}</strong><p>{event.detail}</p>{event.destination&&<button className="mini-btn" onClick={()=>navigate(event.destination)}>Open results</button>}<button className="mini-btn" aria-label="Dismiss notification" onClick={()=>setToasts(old=>old.filter(e=>e.id!==event.id))}>Dismiss</button></div>)}</div></>;
}
