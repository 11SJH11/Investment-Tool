import { useEffect } from 'react';
import { api, backendFileUrl } from '../../api/client';
import { pnlSummary, rValue } from './journalUtils';
export function useUnsaved(dirty, onDirtyChange) {
  useEffect(()=>{onDirtyChange?.(dirty);return()=>onDirtyChange?.(false);},[dirty,onDirtyChange]);
  useEffect(()=>{const warn=e=>{if(dirty){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);},[dirty]);
}
export function Summary({data={}}) {
  const values=[['Trades',data.trades??0],['Wins / losses / breakeven',`${data.wins??0} / ${data.losses??0} / ${data.breakevens??0}`],['Win rate',data.win_rate==null?'—':`${data.win_rate.toFixed(1)}%`],['Average R',rValue(data.average_r)],['Total R',rValue(data.total_r)],['Profit factor (R)',data.profit_factor_r==='inf'?'∞':data.profit_factor_r==null?'—':Number(data.profit_factor_r).toFixed(2)],['Recorded P&L',pnlSummary(data)]];
  return <div><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{values.map(([label,value])=><div key={label} className="rounded-lg border border-stone-200 bg-white p-4"><p className="text-xs text-stone-500">{label}</p><p className="mt-1 text-lg font-semibold">{value}</p></div>)}</div><p className="mt-2 text-xs text-stone-500">R available for {data.r_trades??0} closed trades; P&L for {data.pnl_trades??0}. Win rate excludes breakeven and {data.unknown_outcomes??0} unknown outcomes. Currency totals remain separate. Small samples do not establish an edge.</p></div>;
}
export function Attachments({ownerType,ownerId,items=[],onChanged,onError}) {
  const act=async fn=>{try{await fn();await onChanged();}catch(e){onError(e.message);}};
  return <section className="mt-5"><div className="flex flex-wrap justify-between gap-3"><h4 className="font-semibold">Screenshots</h4><label className="cursor-pointer text-sm text-blue-700">+ Add screenshot<input className="hidden" type="file" accept="image/*" onChange={e=>{const file=e.target.files?.[0];if(file)void act(()=>api.uploadJournalAttachment(ownerType,ownerId,'general',file));e.target.value='';}}/></label></div><div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{items.map(img=><div key={img.id} className="rounded-lg border p-2"><a href={backendFileUrl(img.url)} target="_blank" rel="noreferrer"><img alt={img.caption||img.original_name||'Journal screenshot'} src={backendFileUrl(img.url)} className="max-h-64 w-full bg-stone-950 object-contain"/></a><div className="mt-2 flex justify-between gap-2 text-xs"><span>{img.slot||'General'} · {img.caption||img.original_name}</span><button type="button" className="text-red-700" onClick={()=>{if(confirm('Remove this screenshot?'))void act(()=>api.deleteJournalAttachment(img.id));}}>Remove</button></div></div>)}</div>{!items.length&&<p className="mt-2 text-sm text-stone-500">No screenshots yet.</p>}</section>;
}
