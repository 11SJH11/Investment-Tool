import { Field } from './ReviewFields';
import { sourceLabel } from './journalUtils';
export const emptyFilters={dimensions_json:'{}',date_from:'',date_to:''};
const dimensions=[['ticker','Instrument'],['account','Account'],['external_provider','Broker'],['environment','Environment'],['source','Source'],['playbook_id','Playbook'],['setup','Setup'],['setup_grade','Grade'],['plan_followed','Plan adherence'],['direction','Direction'],['session_time','Session'],['market_condition','Market regime'],['structure_alignment','Market structure'],['entry_relativity','Entry relativity'],['shift','Shift'],['confluences','Confluences'],['mistakes','Mistakes'],['emotions','Emotion'],['weekday','Weekday'],['entry_hour','Entry hour'],['month','Month'],['result','Result']];
export default function JournalFilters({value,onChange,options={},playbooks=[]}) {
 const selected=JSON.parse(value.dimensions_json||'{}');
 const toggle=(key,item)=>{const old=selected[key]||[];onChange({...value,dimensions_json:JSON.stringify({...selected,[key]:old.includes(item)?old.filter(v=>v!==item):[...old,item]})});};
 const label=(key,v)=>key==='source'?sourceLabel(v):key==='playbook_id'?(playbooks.find(p=>String(p.id)===v)?.title||v):v;
 return <details className="rounded-xl border border-stone-200 bg-white p-4" open><summary className="cursor-pointer text-sm font-medium">Filter trades</summary>
   <p className="mt-2 text-xs text-stone-500">Any selected value within a field; all selected fields must match. Dates and time filters use the Journal timezone.</p>
   <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{dimensions.map(([key,title])=><details key={key} className="min-w-0 rounded border p-2"><summary className="cursor-pointer text-xs font-medium">{title} {(selected[key]||[]).length?`(${selected[key].length})`:': All'}</summary><div className="mt-2 max-h-44 space-y-1 overflow-y-auto">{[...new Set([...(options[key]||[]),...(selected[key]||[])])].map(v=><label key={v} className="flex items-start gap-2 text-xs"><input type="checkbox" checked={(selected[key]||[]).includes(v)} onChange={()=>toggle(key,v)}/><span className="break-words">{label(key,v)}</span></label>)}{!(options[key]||[]).length&&<p className="text-xs text-stone-500">No recorded values</p>}</div></details>)}
   {['date_from','date_to'].map(k=><Field key={k} label={k==='date_from'?'From':'To'}><input className="input" type="date" value={value[k]||''} onChange={e=>onChange({...value,[k]:e.target.value})}/></Field>)}</div>
   <button type="button" className="mt-3 text-xs text-blue-700" onClick={()=>onChange({...emptyFilters})}>Clear filters</button>
 </details>;
}
