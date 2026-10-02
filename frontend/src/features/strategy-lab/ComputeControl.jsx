import {useEffect,useState} from 'react';
import {jobStatus} from './researchPolling.js';
import {api} from '../../api/client.js';

const OPTIONS=[['auto_conservative','Auto · conservative'],['auto_performance','Auto · performance'],['1','1 worker'],['2','2 workers'],['4','4 workers'],['6','6 workers'],['8','8 workers']];
export default function ComputeControl({compact=false,onError}){
  const [settings,setSettings]=useState(null),[busy,setBusy]=useState(false);
  useEffect(()=>jobStatus.subscribe((data,error)=>{if(error)onError?.(error.message);else if(data?.compute)setSettings(data.compute)}),[]);
  const save=async mode=>{setBusy(true);try{setSettings(await api.saveComputeSettings(mode));await jobStatus.refresh();}catch(e){onError?.(e.message);}finally{setBusy(false);}};
  if(!settings)return <span className="text-xs text-stone-500">Compute setting loading…</span>;
  return <div className={compact?'flex flex-wrap items-end gap-2':'grid gap-3 sm:grid-cols-[260px_1fr] items-end'}><label className="block text-xs"><span className="mb-1 block font-medium text-stone-500">Backtest CPU workers</span><select className="input" disabled={busy} value={settings.mode} onChange={e=>save(e.target.value)}>{OPTIONS.map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label><p className="text-xs text-stone-500">CPU budget: <strong>{settings.configured_budget??settings.resolved_workers}</strong>. Reserved: {settings.used_workers??0}. Simulations waiting: {settings.queued_simulations??0}. {settings.note}</p></div>;
}
