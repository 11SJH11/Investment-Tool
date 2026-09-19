import {useState} from 'react';
import {useUIPreference} from '../../app/useUIPreference.js';
import {api} from '../../api/client';
import {formatInZone} from '../../utils/timezones';
import {moneyCurrency,sourceLabel,rValue,resultTone} from './journalUtils';
import TradeDetail from './TradeDetail';
import ExecutionForm from './ExecutionForm';
import {Summary,useUnsaved} from './JournalShared';
import DataTable from '../../components/table/DataTable.jsx';
export default function TradesView({timeZone,playbooks,revision,onChanged,onDirtyChange,report,loading,error:loadError,columns,table}) {
  const [selected,setSelected]=useState(null),[creating,setCreating]=useState(false),[dirty,setDirty]=useState(false),[error,setError]=useState('');
  const [view,setView]=useUIPreference('journal.view','table');const rows=report?.trades||[];
  useUnsaved(dirty,onDirtyChange);
  const navigate=fn=>{if(!dirty||confirm('Discard unsaved trade changes?')){setDirty(false);fn();}};
  const open=async id=>{try{setSelected(await api.journalTrade(id));setCreating(false);}catch(e){setError(e.message);}};
  const remove=async t=>{if(!confirm('Delete this Journal record and its screenshots?'))return;try{await api.deleteJournalTrade(t.id);if(selected?.id===t.id)setSelected(null);onChanged();}catch(e){setError(e.message);}};
  return <div className="space-y-5"><Summary data={report?.summary}/><div className="ui-toolbar"><span className="muted text-sm">{rows.length} matching trades</span>{['table','cards'].map(v=><button key={v} className={`mini-btn ${view===v?'active-btn':''}`} onClick={()=>setView(v)}>{v==='cards'?'Cards':'Table'}</button>)}<button className="mini-btn ledger-primary text-white" onClick={()=>navigate(()=>{setCreating(true);setSelected(null);})}>+ Log trade</button></div>
    {(error||loadError)&&<p role="alert" className="text-red-700">{error||loadError}</p>}
    {creating&&<ExecutionForm timeZone={timeZone} onDirtyChange={setDirty} onCancel={()=>navigate(()=>setCreating(false))} onSaved={t=>{setDirty(false);setCreating(false);setSelected(t);onChanged();}}/>}
    {selected&&<TradeDetail key={selected.id} trade={selected} timeZone={timeZone} playbooks={playbooks} revision={revision} onDirtyChange={setDirty} onClose={()=>navigate(()=>setSelected(null))} onChanged={onChanged}/>}
    {loading&&<p role="status" className="muted text-sm">Updating filtered trades…</p>}
    {view==='table'?<DataTable id="journal" label="Journal trades" rows={rows} columns={columns} controller={table} manual hideSearch primaryAction={{label:'Open',onClick:t=>navigate(()=>void open(t.id))}} actions={t=>[{label:'Delete',onClick:()=>navigate(()=>void remove(t))}]}/>:<div className="grid gap-4 lg:grid-cols-2">{rows.map(t=><article key={t.id} className="insight-panel"><div className="flex justify-between gap-3"><button className="text-lg font-semibold text-blue-700" onClick={()=>navigate(()=>void open(t.id))}>{t.ticker} · {t.direction}</button><span>{t.setup_grade&&`Grade ${t.setup_grade}`}</span></div><p className="mt-2 text-xs muted">{sourceLabel(t.source)} · {t.account} · {formatInZone(t.opened_at,timeZone)}</p><div className="mt-3 ui-toolbar"><span className={resultTone(t.result)}>{t.result||t.status}</span><span>{moneyCurrency(t.pnl_amount,t.account_currency||t.position_currency||'USD')}</span><span>{rValue(t.r_multiple)}</span></div><div className="mt-3 ui-toolbar"><button className="mini-btn" onClick={()=>navigate(()=>void open(t.id))}>Open review</button><button className="mini-btn" onClick={()=>navigate(()=>void remove(t))}>Delete</button></div></article>)}</div>}
  </div>;
}
