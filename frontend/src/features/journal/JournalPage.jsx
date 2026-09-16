import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { TIMEZONE_OPTIONS, resolvedZone } from '../../utils/timezones';
import CalendarView from './CalendarView';
import DailyReviewView from './DailyReviewView';
import PlaybookView from './PlaybookView';
import TradesView from './TradesView';
import AnalysisView from './AnalysisView';
import JournalFilters, { emptyFilters } from './JournalFilters';
import BrokerSyncPanel from './BrokerSyncPanel';
const tabs=['Trades','Analysis','Calendar','Daily Review','Playbook'];
export default function JournalPage({onDirtyChange}) {
  const [tab,setTab]=useState('Trades'),[zone,setZone]=useState(null),[filters,setFilters]=useState({...emptyFilters});
  const [playbooks,setPlaybooks]=useState([]),[options,setOptions]=useState({}),[revision,setRevision]=useState(0),[error,setError]=useState(''),[dirty,setDirty]=useState(false),[day,setDay]=useState(null);
  useEffect(()=>{onDirtyChange?.(dirty);return()=>onDirtyChange?.(false);},[dirty,onDirtyChange]);
  const changed=()=>setRevision(v=>v+1);
  useEffect(()=>{let active=true;api.journalSettings().then(async s=>{const timezone=s.timezone||resolvedZone(localStorage.getItem('ledger.timeZone')||'UTC');if(!s.timezone)await api.saveJournalSettings(timezone);if(active)setZone(timezone);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[]);
  useEffect(()=>{let active=true;Promise.all([api.playbook(),api.journalOptions()]).then(([p,o])=>{if(active){setPlaybooks(p.items||[]);setOptions(o);}}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[revision]);
  const navigate=fn=>{if(!dirty||confirm('Discard unsaved Journal changes?')){setDirty(false);fn();}};
  const openDay=(date,target)=>navigate(()=>{setDay({date,account:filters.account||'Main'});if(target==='Trades')setFilters({...filters,date_from:date,date_to:date});setTab(target);});
  const shared={filters:{...Object.fromEntries(Object.entries(filters).filter(([,v])=>v!=='')),timezone:zone},timeZone:zone,playbooks,options,revision,onChanged:changed,onDirtyChange:setDirty};
  return <div className="max-w-[1550px]"><p className="text-xs uppercase tracking-widest text-stone-500">Trading journal</p><h2 className="mt-1 text-3xl font-semibold">Journal</h2><p className="mt-2 text-sm text-stone-600">Execution facts, your trading plan, and what you learned.</p><BrokerSyncPanel onSynced={changed}/>
    {error&&<p role="alert" className="my-3 text-sm text-red-700">{error}</p>}
    {zone&&<div className="my-4 flex flex-wrap items-center gap-3"><label className="text-sm">Journal timezone <select className="input ml-2 inline-block w-60" value={zone} onChange={e=>{const next=resolvedZone(e.target.value);navigate(()=>{api.saveJournalSettings(next).then(()=>setZone(next)).catch(e=>setError(e.message));});}}>{[...new Set([...TIMEZONE_OPTIONS.filter(x=>x.value!=='local').map(x=>x.value),resolvedZone('local'),zone])].map(z=><option key={z}>{z}</option>)}</select></label><span className="text-xs text-stone-500">Days use entry time. Calendar, Analysis and Daily Review share this timezone.</span></div>}
    <div className="flex flex-wrap gap-1 border-b border-stone-200">{tabs.map(t=><button key={t} onClick={()=>navigate(()=>setTab(t))} className={`border-b-2 px-4 py-2 text-sm ${tab===t?'border-stone-900 font-semibold':'border-transparent text-stone-500'}`}>{t}</button>)}</div>
    {!zone?<p className="py-8 text-stone-500">Loading Journal settings...</p>:<div className="mt-5 space-y-5">{['Trades','Analysis','Calendar'].includes(tab)&&<JournalFilters value={filters} onChange={f=>navigate(()=>setFilters(f))} options={options} playbooks={playbooks}/>}{tab==='Trades'&&<TradesView key={JSON.stringify(filters)+zone} {...shared}/ >}{tab==='Analysis'&&<AnalysisView {...shared}/ >}{tab==='Calendar'&&<CalendarView {...shared} onOpenDay={openDay}/ >}{tab==='Daily Review'&&<DailyReviewView {...shared} initialDay={day}/ >}{tab==='Playbook'&&<PlaybookView {...shared}/ >}</div>}
  </div>;
}
