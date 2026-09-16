import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { formatInZone } from '../../utils/timezones';
import { moneyCurrency, sourceLabel, rValue, resultTone } from './journalUtils';
import TradeDetail from './TradeDetail';
import {TABLE_COLUMNS,loadColumns,saveColumns} from './journalPreferences';
import ExecutionForm from './ExecutionForm';
import { Summary, useUnsaved } from './JournalShared';
export default function TradesView({filters,timeZone,playbooks,revision,onChanged,onDirtyChange}) {
  const [rows,setRows]=useState([]),[summary,setSummary]=useState({}),[total,setTotal]=useState(0),[offset,setOffset]=useState(0),[view,setView]=useState('cards'),[selected,setSelected]=useState(null),[creating,setCreating]=useState(false),[dirty,setDirty]=useState(false),[loading,setLoading]=useState(true),[error,setError]=useState('');
  const [columns,setColumns]=useState(()=>loadColumns(localStorage));
  useEffect(()=>saveColumns(localStorage,columns),[columns]);
  const cell=(trade,key)=>{
    if(key==='opened_at')return formatInZone(trade.opened_at,timeZone);
    if(key==='source')return sourceLabel(trade.source);
    if(key==='currency')return trade.account_currency||trade.position_currency||'USD';
    if(key==='pnl_amount')return moneyCurrency(trade.pnl_amount,trade.account_currency||trade.position_currency||'USD');
    if(key==='r_multiple')return rValue(trade.r_multiple);
    if(key==='environment'||key==='exit_reason')return trade.source_metadata?.[key]||'Unavailable';
    if(key==='duration'){const duration=(Date.parse(trade.closed_at)-Date.parse(trade.opened_at))/60000;return Number.isFinite(duration)&&duration>=0?duration.toFixed(1):'Unavailable';}
    return trade[key]??'Unavailable';
  };
  const query=JSON.stringify(filters);
  useUnsaved(dirty,onDirtyChange);
  useEffect(()=>{setOffset(0);},[query]);
  useEffect(()=>{let active=true;setLoading(true);setError('');Promise.all([api.journalTrades({...JSON.parse(query),limit:50,offset}),api.journalAnalytics(JSON.parse(query))]).then(([t,a])=>{if(active){setRows(t.items);setTotal(t.total);setSummary(a);}}).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[query,offset,revision]);
  const navigate=fn=>{if(!dirty||confirm('Discard unsaved trade changes?')){setDirty(false);fn();}};
  const open=async id=>{try{setSelected(await api.journalTrade(id));setCreating(false);}catch(e){setError(e.message);}};
  const remove=async t=>{if(!confirm('Delete this Journal record and its screenshots?'))return;try{await api.deleteJournalTrade(t.id);if(selected?.id===t.id)setSelected(null);onChanged();}catch(e){setError(e.message);}};
  const facts=t=><><span className={resultTone(t.result)}>{t.result||t.status}</span><span>{moneyCurrency(t.pnl_amount,t.account_currency||t.position_currency||'USD')}</span><span>{rValue(t.r_multiple)}</span></>;
  return <div className="space-y-5"><Summary data={summary}/><div className="flex flex-wrap items-center justify-between gap-3"><p className="text-sm text-stone-500">{total} matching trades</p><div className="flex gap-2">{['cards','table'].map(v=><button key={v} className={`mini-btn ${view===v?'active-btn':''}`} onClick={()=>setView(v)}>{v==='cards'?'Cards':'Table'}</button>)}<button className="mini-btn" onClick={()=>navigate(()=>{setCreating(true);setSelected(null);})}>+ Log trade</button></div></div>
    {error&&<p role="alert" className="rounded border border-red-200 p-3 text-red-700">{error}</p>}
    {creating&&<ExecutionForm timeZone={timeZone} onDirtyChange={setDirty} onCancel={()=>navigate(()=>setCreating(false))} onSaved={t=>{setDirty(false);setCreating(false);setSelected(t);onChanged();}}/>}
    {selected&&<TradeDetail key={selected.id} trade={selected} timeZone={timeZone} playbooks={playbooks} revision={revision} onDirtyChange={setDirty} onClose={()=>navigate(()=>setSelected(null))} onChanged={onChanged}/>}
    {loading?<p role="status" className="p-8 text-center text-stone-500">Loading trades...</p>:!rows.length?<div className="rounded-xl border border-dashed p-10 text-center"><h3 className="font-medium">No trades match these filters</h3><p className="mt-2 text-sm text-stone-500">Clear filters, log a manual trade, finish a Replay trade, or sync a configured broker.</p></div>:view==='cards'?<div className="grid gap-4 lg:grid-cols-2">{rows.map(t=><article key={t.id} className="rounded-xl border border-stone-200 bg-white p-5"><div className="flex justify-between gap-3"><div><button className="text-lg font-semibold text-blue-700" onClick={()=>navigate(()=>void open(t.id))}>{t.ticker} · {t.direction}</button><p className="mt-1 text-xs text-stone-500">{sourceLabel(t.source)} · {t.account}</p></div><span className="text-sm">{t.setup_grade&&`Grade ${t.setup_grade}`}</span></div><p className="mt-3 text-sm text-stone-600">{formatInZone(t.opened_at,timeZone)} · {t.playbook_title||t.setup||'No Playbook linked'}</p><div className="mt-3 flex flex-wrap gap-4 font-medium">{facts(t)}</div><div className="mt-4 flex justify-between text-xs"><button className="text-blue-700" onClick={()=>navigate(()=>void open(t.id))}>Open review</button><button className="text-stone-500" onClick={()=>navigate(()=>void remove(t))}>Delete</button></div></article>)}</div>:<div className="min-w-0 rounded-xl border bg-white"><details className="p-3"><summary className="cursor-pointer text-sm">Visible columns</summary><div className="mt-3 grid gap-2 sm:grid-cols-3">{TABLE_COLUMNS.map(([key,label])=><label key={key} className="flex gap-2 text-xs"><input type="checkbox" checked={columns.includes(key)} disabled={columns.length===1&&columns.includes(key)} onChange={()=>setColumns(old=>old.includes(key)?old.filter(v=>v!==key):TABLE_COLUMNS.map(([k])=>k).filter(k=>k===key||old.includes(k)))}/>{label}</label>)}</div></details><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{columns.map(key=><th key={key} className="whitespace-nowrap p-3">{TABLE_COLUMNS.find(([k])=>k===key)?.[1]}</th>)}<th className="p-3">Review</th></tr></thead><tbody>{rows.map(t=><tr key={t.id} className="border-t">{columns.map(key=><td key={key} className="whitespace-nowrap p-3">{cell(t,key)}</td>)}<td className="whitespace-nowrap p-3"><button className="text-blue-700" onClick={()=>navigate(()=>void open(t.id))}>Open review</button><button className="ml-3 text-red-700" onClick={()=>navigate(()=>void remove(t))}>Delete</button></td></tr>)}</tbody></table></div></div>}

    <div className="flex items-center justify-end gap-3 text-sm"><button className="mini-btn" disabled={loading||!offset} onClick={()=>setOffset(Math.max(0,offset-50))}>Previous</button><span>{total?`${offset+1}–${Math.min(offset+50,total)} of ${total}`:'0 trades'}</span><button className="mini-btn" disabled={loading||offset+50>=total} onClick={()=>setOffset(offset+50)}>Next</button></div>
  </div>;
}
