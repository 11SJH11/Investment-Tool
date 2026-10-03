import {useEffect,useRef,useState} from 'react';
import {api} from '../../api/client';
import {BROKER_NAMES,canConfigureConnection,canSelectAccount,connectionSummary,connectionHint} from './brokerConnectionUtils.js';
const date=value=>value?new Date(value).toLocaleString():'Not yet';

export default function BrokerProfilesPanel({destination,onSynced}) {
  const [profiles,setProfiles]=useState([]),[busy,setBusy]=useState(''),[error,setError]=useState(''),[message,setMessage]=useState('');
  const [accounts,setAccounts]=useState({}),[tested,setTested]=useState({});
  const callback=useRef(onSynced);callback.current=onSynced;
  const refresh=()=>api.brokerProfiles().then(r=>setProfiles(r.items));
  useEffect(()=>{let active=true,previous;
    const poll=()=>api.brokerProfiles().then(r=>{
      if(!active)return;
      setProfiles(r.items);
      const signature=JSON.stringify(r.items.map(p=>p.last_success_at));
      if(previous&&signature!==previous)callback.current?.();previous=signature;
    }).catch(e=>{if(active)setError(e.message);});
    poll();const timer=setInterval(poll,10000);return()=>{active=false;clearInterval(timer);};
  },[]);
  const action=async(p,fn)=>{
    setBusy(p.profile_id);setError('');setMessage('');
    try{await fn();}catch(e){setError(e.message);}
    finally{try{await refresh();}catch(e){setError(e.message);}setBusy('');}
  };
  const sync=p=>action(p,async()=>{
    const r=await api.syncBrokerProfile(p.profile_id);
    setMessage(`${BROKER_NAMES[p.provider]}: ${r.status}. Imported ${r.created??0}; refreshed ${r.updated??0}.`);
    callback.current?.();
  });
  const test=p=>action(p,async()=>{
    const r=await api.testBrokerConnection(p.profile_id);
    setAccounts(old=>({...old,[p.profile_id]:r.items}));
    setTested(old=>({...old,[p.profile_id]:'Connected'}));
    setMessage('Read-only connection verified. No history was imported.');
  });
  const configure=(p,enabled,environment=p.environment)=>action(p,async()=>{
    await api.configureBrokerConnection(p.profile_id,{enabled,environment});
    setAccounts(old=>({...old,[p.profile_id]:[]}));setTested(old=>({...old,[p.profile_id]:''}));
    setMessage(enabled?'Connection preferences saved. Credentials are configured on the backend.':'Disconnected locally. Imported data is preserved. Credentials in backend environment configuration are unchanged.');
  });
  const select=(p,key)=>action(p,async()=>{
    await api.selectBrokerAccount(p.profile_id,key);setMessage('Verified account selected.');
  });
  const schedule=(p,changes)=>action(p,()=>api.brokerSchedule(p.profile_id,{enabled:p.auto_sync.enabled,interval_seconds:p.auto_sync.interval_seconds,...changes}));
  return <section className="mt-5 rounded-xl border bg-white p-4">
    <h3 className="font-semibold">Broker connections - read only</h3>
    <p className="mt-2 text-xs text-stone-600">Automatic reconciliation runs on the backend while Ledger is running. No orders are placed or changed. Secrets are never stored in browser preferences.</p>
    <div className="mt-3 space-y-3">{profiles.filter(p=>!destination||p.destination===destination).map(p=>{
      const configurable=canConfigureConnection(p.provider), disabled=Boolean(busy)||p.auto_sync?.status==='syncing';
      return <article key={p.profile_id} className="rounded border p-3" aria-label={`${BROKER_NAMES[p.provider]} connection`}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0"><strong className="text-sm">{BROKER_NAMES[p.provider]} / {p.environment}</strong>
            <p className="text-xs text-stone-500">{p.profile_id} / {p.destination==='portfolio'?'Investment Portfolio':'Journal'} / {connectionSummary(p)}</p>
            <p className="text-xs">Status: {tested[p.profile_id]||p.status?.replaceAll('_',' ')}</p>
            {p.account&&<p className="text-xs">{p.account}</p>}
          </div>
          <div className="flex flex-wrap gap-2">
            {configurable&&<button className="mini-btn" disabled={disabled||!p.configured} onClick={()=>test(p)}>Test connection</button>}
            <button className="mini-btn" disabled={disabled||!p.configured||!p.supported} onClick={()=>sync(p)}>{busy===p.profile_id?'Working...':'Sync now'}</button>
            {configurable&&<button className="mini-btn" disabled={disabled} onClick={()=>configure(p,!p.configured||p.disconnected)}>{p.configured&&!p.disconnected?'Disconnect':'Enable connection'}</button>}
          </div>
        </div>
        {configurable&&<p className="mt-2 max-w-3xl text-xs text-stone-600">{connectionHint(p.provider)}</p>}
        {p.reason&&<p className="mt-1 max-w-3xl text-xs text-stone-600">{p.reason}</p>}
        {configurable&&<div className="mt-3 flex flex-wrap gap-3 text-xs">
          <label>Environment <select aria-label={`${BROKER_NAMES[p.provider]} environment`} className="input" value={p.environment} disabled={disabled} onChange={e=>configure(p,p.configured,e.target.value)}><option value="demo">Demo</option><option value="live">Live (read only)</option></select></label>
          {canSelectAccount(p.provider)&&accounts[p.profile_id]?.length>0&&<label>Account <select className="input" aria-label={`${BROKER_NAMES[p.provider]} account`} disabled={disabled} value={p.account_key||''} onChange={e=>e.target.value&&select(p,e.target.value)}><option value="">Select a verified account</option>{accounts[p.profile_id].map(a=><option key={a.account_key} value={a.account_key}>{a.label} / {a.currency}</option>)}</select></label>}
        </div>}
        <p className="mt-2 text-xs">Last successful sync: {date(p.last_success_at)}</p>
        {p.error_category&&<p className="text-xs">Last error category: {p.error_category.replaceAll('_',' ')}</p>}
        {p.auto_sync&&<div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
          <label><input type="checkbox" checked={p.auto_sync.enabled} disabled={disabled||!p.supported} onChange={e=>schedule(p,{enabled:e.target.checked})}/> Auto-sync</label>
          <label>Interval (seconds) <input key={p.auto_sync.interval_seconds} className="input w-24" type="number" min={p.auto_sync.minimum_seconds} max="86400" defaultValue={p.auto_sync.interval_seconds} disabled={disabled} onBlur={e=>{const value=Number(e.target.value);if(value!==p.auto_sync.interval_seconds)schedule(p,{interval_seconds:value});}}/></label>
          <span>Status: {p.auto_sync.status} / Next: {date(p.auto_sync.next_sync_at)}</span>
        </div>}
        {p.error&&<p className="mt-2 text-xs text-red-700">{p.error}</p>}
      </article>;
    })}</div>
    {error&&<p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}{message&&<p role="status" className="mt-3 text-sm">{message}</p>}
  </section>;
}
