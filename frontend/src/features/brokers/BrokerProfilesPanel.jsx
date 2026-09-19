import {useEffect,useRef,useState} from 'react';
import {api} from '../../api/client';
const names={oanda:'OANDA',trading212:'Trading 212',tradovate:'Tradovate'};
const date=value=>value?new Date(value).toLocaleString():'Not yet';
export default function BrokerProfilesPanel({destination,onSynced}) {
  const [profiles,setProfiles]=useState([]),[busy,setBusy]=useState(''),[error,setError]=useState(''),[message,setMessage]=useState('');
  const callback=useRef(onSynced);callback.current=onSynced;
  const refresh=()=>api.brokerProfiles().then(r=>setProfiles(r.items));
  useEffect(()=>{let active=true,previous;
    const poll=()=>api.brokerProfiles().then(r=>{if(!active)return;setProfiles(r.items);const signature=JSON.stringify(r.items.map(p=>p.last_success_at));if(previous&&signature!==previous)callback.current?.();previous=signature;}).catch(e=>{if(active)setError(e.message);});
    poll();const timer=setInterval(poll,10000);return()=>{active=false;clearInterval(timer);};
  },[]);
  const sync=async p=>{setBusy(p.profile_id);setError('');setMessage('');try{const r=await api.syncBrokerProfile(p.profile_id);setMessage(`${names[p.provider]}: ${r.status}. Imported ${r.created??0}; refreshed ${r.updated??0}.`);callback.current?.();}catch(e){setError(e.message);}finally{try{await refresh();}catch(e){setError(e.message);}setBusy('');}};
  const schedule=async(p,changes)=>{try{setError('');await api.brokerSchedule(p.profile_id,{enabled:p.auto_sync.enabled,interval_seconds:p.auto_sync.interval_seconds,...changes});await refresh();}catch(e){setError(e.message);}};
  return <section className="mt-5 rounded-xl border bg-white p-4"><h3 className="font-semibold">Broker connections · read only</h3><p className="mt-2 text-xs text-stone-600">Automatic reconciliation runs on the backend while Ledger is running, even after you leave this page. No orders are placed or changed.</p>
    <div className="mt-3 space-y-3">{profiles.filter(p=>!destination||p.destination===destination).map(p=><div key={p.profile_id} className="flex flex-wrap items-center justify-between gap-3 rounded border p-3"><div className="min-w-0"><strong className="text-sm">{names[p.provider]} · {p.environment}</strong><p className="text-xs text-stone-500">{p.profile_id} · {p.destination==='portfolio'?'Investment Portfolio':'Journal'} · {p.status?.replaceAll('_',' ')}</p>{p.account&&<p className="text-xs">{p.account}</p>}{p.reason&&<p className="mt-1 max-w-2xl text-xs text-stone-600">{p.reason}</p>}<p className="text-xs">Last successful sync: {date(p.last_success_at)}</p>{p.auto_sync&&<div className="mt-2 flex flex-wrap items-center gap-3 text-xs"><label><input type="checkbox" checked={p.auto_sync.enabled} disabled={!p.supported} onChange={e=>schedule(p,{enabled:e.target.checked})}/> Auto-sync</label><label>Interval (seconds) <input key={p.auto_sync.interval_seconds} className="input w-24" type="number" min={p.auto_sync.minimum_seconds} max="86400" defaultValue={p.auto_sync.interval_seconds} onBlur={e=>{const value=Number(e.target.value);if(value!==p.auto_sync.interval_seconds)schedule(p,{interval_seconds:value});}}/></label><span>Status: {p.auto_sync.status} · Next: {date(p.auto_sync.next_sync_at)}</span></div>}{p.error&&<p className="text-xs text-red-700">{p.error}</p>}</div><button className="mini-btn" disabled={Boolean(busy)||!p.configured||!p.supported||p.auto_sync?.status==='syncing'} onClick={()=>sync(p)}>{busy===p.profile_id?'Syncing history…':'Sync now'}</button></div>)}</div>
    {error&&<p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}{message&&<p role="status" className="mt-3 text-sm">{message}</p>}
  </section>;
}
