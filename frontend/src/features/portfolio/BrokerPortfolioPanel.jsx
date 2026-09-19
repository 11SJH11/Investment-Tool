import {useEffect,useState} from 'react';
import {api} from '../../api/client';
import BrokerProfilesPanel from '../brokers/BrokerProfilesPanel';
import {moneyCurrency} from '../journal/journalUtils';
import {activitySemantics, brokerDate, percent, positionMetrics, returnPercent} from './brokerPortfolioUtils';

function amount(value, currency) { return Number.isFinite(value) && currency ? `${moneyCurrency(value,currency)} ${currency}` : 'Unavailable'; }
function Metrics({items}) { return <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">{items.map(([label,value])=><div key={label} className="min-w-0 rounded bg-stone-50 p-3"><dt className="text-xs text-stone-600">{label}</dt><dd className="mt-1 break-words font-semibold">{value}</dd></div>)}</dl>; }

export default function BrokerPortfolioPanel() {
  const [accounts,setAccounts]=useState([]),[account,setAccount]=useState(''),[kind,setKind]=useState('position'),[offset,setOffset]=useState(0),[data,setData]=useState({items:[],total:0}),[revision,setRevision]=useState(0),[error,setError]=useState(''),[loading,setLoading]=useState(false),[selected,setSelected]=useState(null),[note,setNote]=useState(''),[tags,setTags]=useState('');
  useEffect(()=>{let active=true;api.brokerPortfolioAccounts().then(r=>{if(active){setAccounts(r.items);setAccount(a=>a||r.items[0]?.account_key||'');}}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[revision]);
  useEffect(()=>{if(!account)return;let active=true;setLoading(true);api.brokerPortfolioRecords(account,kind,offset).then(r=>{if(active)setData(r);}).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[account,kind,offset,revision]);
  const change=fn=>{if(!selected||confirm('Discard unsaved Portfolio review changes?')){setSelected(null);fn();}};
  const save=async()=>{try{await api.saveBrokerPortfolioReview(selected.id,{note,tags:tags.split(',').map(x=>x.trim()).filter(Boolean)});setSelected(null);setRevision(v=>v+1);}catch(e){setError(e.message);}};
  const current=accounts.find(a=>a.account_key===account),s=current?.summary||{},currency=s.currency;
  const zone=localStorage.getItem('ledger.timeZone')||'UTC';
  const review=r=>change(()=>{setSelected(r);setNote(r.note);setTags(r.tags.join(', '));});
  const details=r=><details className="mt-2 text-xs"><summary className="cursor-pointer">Execution/provider details</summary><p className="break-all">Provider ID: {r.external_id}</p><pre className="max-w-full whitespace-pre-wrap break-all">{JSON.stringify(r.facts,null,2)}</pre></details>;
  return <section className="mt-5"><BrokerProfilesPanel destination="portfolio" onSynced={()=>setRevision(v=>v+1)}/>{error&&<p role="alert" className="text-red-700">{error}</p>}
    {current&&<div className="mt-4 min-w-0 rounded-xl border bg-white p-4"><h3 className="font-semibold">Broker Portfolio snapshot</h3><p className="mt-1 text-xs text-stone-500" title={current.synced_at}>Provider facts as of {brokerDate(current.synced_at,zone)} ({zone}). Historical records do not add to holdings. Amounts retain their reported currencies.</p>
      <div className="my-3 flex flex-wrap gap-3"><label className="text-xs">Broker account<select className="input mt-1" value={account} onChange={e=>change(()=>{setAccount(e.target.value);setOffset(0);})}>{accounts.map(a=><option key={a.account_key} value={a.account_key}>{a.label}</option>)}</select></label><label className="text-xs">Records<select className="input mt-1" value={kind} onChange={e=>change(()=>{setKind(e.target.value);setOffset(0);})}>{[['position','Positions'],['orders','Orders / fills'],['dividends','Dividends'],['transactions','Cash transactions']].map(([k,l])=><option key={k} value={k}>{l}</option>)}</select></label></div>
      <Metrics items={[
        ['Account value',amount(s.totalValue,currency)],['Investments value',amount(s.investments?.currentValue,currency)],
        ['Open cost basis',amount(s.investments?.totalCost,currency)],['Unrealised P&L',amount(s.investments?.unrealizedProfitLoss,currency)],
        ['Unrealised return',percent(currency ? returnPercent(s.investments?.unrealizedProfitLoss,s.investments?.totalCost) : null)],
        ['Realised P&L',amount(s.investments?.realizedProfitLoss,currency)],['Available cash',amount(s.cash?.availableToTrade,currency)],
        ['Dividends total','Unavailable in account summary'],['Total return','Unavailable: no complete cash-flow return model'],
      ]}/>
      <p className="mt-2 text-xs text-stone-500">Unrealised return = reported unrealised P&L / reported open cost. Dividend payments are available in Dividends records; a page of history is not an account total.</p>
      {selected&&<div className="my-4 rounded border p-3"><h4 className="font-medium">Notes and tags · record {selected.id}</h4><label className="block text-sm">Note<textarea className="input" value={note} onChange={e=>setNote(e.target.value)}/></label><label className="block text-sm">Tags (comma separated)<input className="input" value={tags} onChange={e=>setTags(e.target.value)}/></label><button className="mini-btn mt-2" onClick={save}>Save Portfolio review</button></div>}
      {loading?<p className="py-4">Loading broker records…</p>:kind==='position'?<div className="mt-4 grid gap-4 xl:grid-cols-2">{data.items.map(r=>{const p=positionMetrics(r.facts);return <article key={r.id} className="min-w-0 rounded border p-4"><h4 className="break-words font-semibold">{p.name}</h4><p className="mb-3 text-sm">{p.ticker} · {p.quantity??'Unavailable'} shares{!r.active&&' (previous snapshot; no longer held)'}</p><Metrics items={[
        ['Average cost / share',amount(p.averageCost,p.priceCurrency)],['Current price / share',amount(p.currentPrice,p.priceCurrency)],
        ['Invested / open cost',amount(p.invested,p.walletCurrency)],['Current value',amount(p.value,p.walletCurrency)],
        ['Unrealised P&L',amount(p.pnl,p.walletCurrency)],['Unrealised return',percent(p.returnPct)],
      ]}/><button className="mt-3 text-sm text-blue-700" onClick={()=>review(r)}>Notes / tags</button>{details(r)}{r.note&&<p className="mt-2 whitespace-pre-wrap break-words text-xs">{r.note}</p>}</article>;})}</div>:<div className="mt-4 overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{['Instrument / type','Action / direction','Date','Quantity','Price','Reported value','Review / details'].map(v=><th key={v} className="p-2">{v}</th>)}</tr></thead><tbody>{data.items.map(r=>{const f=r.facts,o=f.order||{},fill=f.fill||{},inst=f.instrument||o.instrument||{},wallet=f.walletImpact||fill.walletImpact||{};return <tr key={r.id} className="border-t"><td className="p-2">{inst.name||inst.ticker||f.ticker||o.ticker||activitySemantics(f,kind).type}</td><td className="p-2 font-medium">{activitySemantics(f,kind).direction}</td><td className="p-2">{brokerDate(fill.filledAt||f.paidOn||f.dateTime||f.createdAt||o.createdAt,zone)}</td><td className="p-2">{f.quantity??fill.quantity??o.quantity??'—'}</td><td className="p-2">{amount(fill.price,inst.currency||o.currency)}</td><td className="p-2">{amount(f.amount??wallet.netValue,f.currency||wallet.currency)}</td><td className="p-2"><button className="text-blue-700" onClick={()=>review(r)}>Notes / tags</button>{details(r)}{r.note&&<p className="max-w-xs whitespace-pre-wrap break-words text-xs">{r.note}</p>}</td></tr>;})}</tbody></table></div>}
      {!loading&&!data.items.length&&<p className="mt-4 text-sm text-stone-500">No records in this account snapshot.</p>}
      <div className="mt-3 flex gap-3 text-xs"><button disabled={loading||!offset} onClick={()=>setOffset(v=>Math.max(0,v-100))}>Previous</button><span>{data.total} records</span><button disabled={loading||offset+100>=data.total} onClick={()=>setOffset(v=>v+100)}>Next</button></div>
    </div>}
  </section>;
}
