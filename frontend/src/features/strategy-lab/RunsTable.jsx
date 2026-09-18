import {useMemo} from 'react';
import {useUIPreference} from '../../app/useUIPreference.js';
import {Button,Section,PageToolbar} from '../../components/ui.jsx';
import {filterRuns} from './backtest-workflow.js';

const COLUMNS=[
  ['name','Run','text'],['status','Status','category'],['strategy_name','Strategy','category'],
  ['symbols','Symbol','category'],['start_date','Period start','date'],['end_date','Period end','date'],
  ['test_role','Role','category'],['trades','Trades','number'],['win_rate_pct','Win rate %','number'],
  ['expectancy_r','Avg R','number'],['total_r','Total R','number'],['profit_factor_r','Profit factor','number'],
  ['return_pct','Return %','number'],['max_drawdown_pct','Max DD %','number'],['created_at','Created','date'],
  ['experiment_group','Experiment','text'],['tags','Tags','text'],['primary_timeframe','TF','category'],
];
export default function RunsTable({runs,selected,toggle,onOpen,onUseSettings,onRemove}) {
  const [filters,setFilters]=useUIPreference('runs.filters',{});
  const [sort,setSort]=useUIPreference('runs.sort',{key:'created_at',direction:'desc'});
  const [columns,setColumns]=useUIPreference('runs.columns',COLUMNS.slice(0,15).map(c=>c[0]));
  const visible=useMemo(()=>filterRuns(runs,filters,sort),[runs,filters,sort]);
  const set=(key,value)=>setFilters(old=>({...old,[key]:value}));
  return <>
    <Section id="run-columns" title="Visible columns"><PageToolbar>{COLUMNS.map(([key,label])=><label key={key} className="text-xs"><input type="checkbox" checked={columns.includes(key)} onChange={()=>setColumns(old=>old.includes(key)?old.filter(x=>x!==key):[...old,key])}/> {label}</label>)}</PageToolbar></Section>
    <PageToolbar><span className="mt-3 text-xs">{visible.length} matching runs · {selected.length}/12 selected for comparison</span><Button onClick={()=>{setFilters({});setSort({key:'created_at',direction:'desc'});}}>Reset filters</Button></PageToolbar>
    <div className="mt-4 max-w-full overflow-x-auto"><table className="w-full text-xs"><thead><tr><th className="p-3">Compare</th>{COLUMNS.filter(c=>columns.includes(c[0])).map(([key,label,kind])=><th key={key} className="min-w-32 p-3 text-left align-top">
      <button onClick={()=>setSort({key,direction:sort.key===key&&sort.direction==='desc'?'asc':'desc'})}>{label} {sort.key===key?(sort.direction==='asc'?'↑':'↓'):''}</button>
      <details className="mt-2 font-normal"><summary className="cursor-pointer">Filter{filters[key]?' •':''}</summary>
        {kind==='category'?<div className="mt-2 max-h-44 overflow-auto">{[...new Set(runs.flatMap(run=>key==='status'?['completed']:Array.isArray(run[key])?run[key]:[String(run[key]??'')]))].sort().map(value=><label key={value} className="block whitespace-nowrap"><input type="checkbox" checked={(filters[key]||[]).includes(value)} onChange={()=>set(key,(filters[key]||[]).includes(value)?filters[key].filter(v=>v!==value):[...(filters[key]||[]),value])}/> {value}</label>)}</div>:
        kind==='number'||kind==='date'?<div className="mt-2 space-y-2">{kind==='number'&&<select aria-label={`${label} comparison`} className="input" value={filters[key]?.operator||'between'} onChange={e=>set(key,{...filters[key],kind,operator:e.target.value})}><option value="between">Between (inclusive)</option><option value="greater">Greater than minimum</option><option value="less">Less than maximum</option></select>}<input aria-label={`${label} minimum`} className="input" type={kind==='date'?'date':'number'} placeholder="Minimum (≥)" value={filters[key]?.min??''} onChange={e=>set(key,{...filters[key],kind,min:e.target.value})}/><input aria-label={`${label} maximum`} className="input" type={kind==='date'?'date':'number'} placeholder="Maximum (≤)" value={filters[key]?.max??''} onChange={e=>set(key,{...filters[key],kind,max:e.target.value})}/></div>:
        <input className="input mt-2" aria-label={`Search ${label}`} placeholder="Search" value={filters[key]||''} onChange={e=>set(key,e.target.value)}/>}</details>
    </th>)}<th className="p-3">Actions</th></tr></thead><tbody>{visible.map(run=><tr key={run.id} className="border-t border-stone-200"><td className="p-3"><input aria-label={`Compare run ${run.id}`} type="checkbox" checked={selected.includes(run.id)} disabled={!selected.includes(run.id)&&selected.length>=12} onChange={()=>toggle(run.id)}/></td>{COLUMNS.filter(c=>columns.includes(c[0])).map(([key])=><td key={key} className="p-3">{key==='status'?'completed':key==='name'?`#${run.id} ${run.name||'Untitled'}`:Array.isArray(run[key])?run[key].join(', '):typeof run[key]==='number'?Number.isInteger(run[key])?run[key]:run[key].toFixed(2):run[key]??'—'}</td>)}<td className="p-3"><PageToolbar><Button onClick={()=>onOpen(run.id)}>Open</Button><Button onClick={()=>onUseSettings(run.id)}>Use settings</Button><Button onClick={()=>onRemove(run.id)}>Delete</Button></PageToolbar></td></tr>)}</tbody></table></div>
  </>;
}
