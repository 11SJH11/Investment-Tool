import {useEffect,useState} from 'react';
import {api} from '../../api/client';
const names={oanda:'OANDA',trading212:'Trading 212',tradovate:'Tradovate'};
export default function BrokerProfilesPanel({destination,onSynced}) {
  const [profiles,setProfiles]=useState([]),[busy,setBusy]=useState(''),[error,setError]=useState(''),[message,setMessage]=useState('');
  const refresh=()=>api.brokerProfiles().then(r=>setProfiles(r.items));
  useEffect(()=>{let active=true;api.brokerProfiles().then(r=>{if(active)setProfiles(r.items);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[]);
  const sync=async p=>{setBusy(p.profile_id);setError('');setMessage('');try{const r=await api.syncBrokerProfile(p.profile_id);setMessage(`${names[p.provider]}: ${r.status}. Imported ${r.created??0}; refreshed ${r.updated??0}.`);onSynced?.();}catch(e){setError(e.message);}finally{try{await refresh();}catch(e){setError(e.message);}setBusy('');}};
  return <section className="mt-5 rounded-xl border bg-white p-4"><h3 className="font-semibold">Broker connections · read only</h3><p className="mt-2 text-xs text-stone-600">Sync runs only when requested. Configure credentials and additional profiles on the backend. No orders are placed or changed.</p>
    <div className="mt-3 space-y-3">{profiles.filter(p=>!destination||p.destination===destination).map(p=><div key={p.profile_id} className="flex flex-wrap items-center justify-between gap-3 rounded border p-3"><div className="min-w-0"><strong className="text-sm">{names[p.provider]} · {p.environment}</strong><p className="text-xs text-stone-500">{p.profile_id} · {p.destination==='portfolio'?'Investment Portfolio':'Journal'} · {p.status?.replaceAll('_',' ')}</p>{p.account&&<p className="text-xs">{p.account}</p>}{p.reason&&<p className="mt-1 max-w-2xl text-xs text-stone-600">{p.reason}</p>}{p.last_success_at&&<p className="text-xs">Last successful sync: {new Date(p.last_success_at).toLocaleString()}</p>}{p.error&&<p className="text-xs text-red-700">{p.error}</p>}</div><button className="mini-btn" disabled={Boolean(busy)||!p.configured||!p.supported} onClick={()=>sync(p)}>{busy===p.profile_id?'Syncing history…':`Sync ${names[p.provider]}`}</button></div>)}</div>
    {error&&<p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}{message&&<p role="status" className="mt-3 text-sm">{message}</p>}
  </section>;
}
