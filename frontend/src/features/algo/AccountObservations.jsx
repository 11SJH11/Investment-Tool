import {useEffect,useRef,useState} from 'react';
import {createChart,LineSeries,ColorType} from 'lightweight-charts';
import {api} from '../../api/client';
import DataTable from '../../components/table/DataTable';

const money=(v,currency)=>v==null?'Unavailable':`${Number(v).toFixed(2)} ${currency}`;
const columns=[['symbol','Symbol'],['side','Side'],['volume','Lots'],['price_open','Entry'],['price_current','Observed price'],['sl','Stop'],['tp','Target'],['profit','Floating P&L'],['swap','Swap']].map(([key,label])=>({key,label,kind:['symbol','side'].includes(key)?'text':'number'}));
function EquityObservations({history,currency}){
 const host=useRef(null);
 useEffect(()=>{
  const values=new Map(history.filter(p=>p.currency===currency).map(p=>[Math.floor(Date.parse(p.observed_at)/1000),p.equity]));
  const points=[...values].filter(([time,value])=>Number.isFinite(time)&&Number.isFinite(value)).sort((a,b)=>a[0]-b[0]).map(([time,value])=>({time,value}));
  if(!host.current||!points.length)return;
  const styles=getComputedStyle(document.documentElement);
  const chart=createChart(host.current,{autoSize:true,height:230,layout:{background:{type:ColorType.Solid,color:'transparent'},textColor:styles.getPropertyValue('--ledger-text').trim()||'#a8a29e'},timeScale:{timeVisible:true},localization:{timeFormatter:t=>new Date(Number(t)*1000).toISOString()}});
  chart.addSeries(LineSeries,{color:styles.getPropertyValue('--ledger-accent').trim()||'#38bdf8',priceLineVisible:false}).setData(points);
  chart.timeScale().fitContent();return()=>chart.remove();
 },[history,currency]);
 return <div><p className="text-xs muted">Observed account equity · {currency} · UTC · N={history.filter(p=>p.currency===currency).length}. Lines join discrete observations; deposits/withdrawals are included. This is not strategy return or drawdown.</p><div ref={host} className="h-60 min-w-0" aria-label="Observed account equity chart"/></div>;
}

function AccountCard({account,onChanged}){
 const [detail,setDetail]=useState(null),[open,setOpen]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const request=useRef(0);
 useEffect(()=>()=>{request.current++;},[]);
 async function load(refresh=false){
  const revision=++request.current;setBusy(true);setError('');
  try{
   if(refresh)await api.brokerAccountSnapshot(account.profile_id);
   const result=await api.brokerAccountObservations(account.profile_id);
   if(result.snapshot&&(result.snapshot.account_key!==account.account_key||result.snapshot.environment!==account.environment))throw Error('Account selection changed. Refresh monitoring before inspecting this observation.');
   if(revision===request.current){setDetail(result);setOpen(true);if(refresh)onChanged();}
  }catch(e){if(revision===request.current){setError(e.message);if(refresh)onChanged();}}
  finally{if(revision===request.current)setBusy(false);}
 }
 const obs=account.observation, facts=obs?.facts, currency=facts?.currency;
 return <article className="insight-panel space-y-2" aria-label={`${account.profile_id} account observation`}>
  <div className="ui-toolbar"><strong>{account.profile_id} · {account.environment?.toUpperCase()}</strong><div className="flex flex-wrap gap-2"><button className="mini-btn" disabled={busy||!account.account_key} onClick={()=>open?setOpen(false):load()}>{open?'Hide details':'View recorded details'}</button><button className="mini-btn" disabled={busy||!account.configured||!account.account_key} onClick={()=>load(true)}>{busy?'Reading…':'Refresh broker observation'}</button></div></div>
  <p className="text-xs muted">Last history sync: {account.last_success_at??'Never'}. History sync does not refresh account equity.</p>
  {facts?<><div className="grid gap-2 sm:grid-cols-4"><p>Observed balance {money(facts.balance,currency)}</p><p>Observed equity {money(facts.equity,currency)}</p><p>Margin {money(facts.margin,currency)}</p><p>Free margin {money(facts.margin_free,currency)}</p></div><p className="text-xs">{obs.position_count} positions · {obs.pending_order_count} pending orders · Observed {obs.observed_at}. {Date.now()-Date.parse(obs.observed_at)>120000?'Historical observation; refresh for newer facts.':'Recent observation; connection health is not continuously verified.'}</p></>:<p>No recorded account observation. Select a verified account in Settings, then refresh here.</p>}
  {(error||obs?.error_category)&&<p role="alert">{error||'Last account refresh failed.'} Previous facts are retained and may be stale.</p>}
  {open&&detail?.snapshot&&<div className="space-y-3"><p className="text-xs muted">Details observed {detail.snapshot.observed_at}. {detail.snapshot.warning} Account positions include manual trades; none are attributed to T01 by this view. Position P&L is in {detail.snapshot.account.currency}; lots are not monetary exposure.</p>
   <EquityObservations history={detail.history} currency={detail.snapshot.account.currency}/>
   <DataTable id={`algo.account.positions.${account.account_key}`} label="Observed broker positions" columns={columns} rows={detail.snapshot.positions.map(p=>({...p,id:p.ticket,side:p.type===0?'BUY':p.type===1?'SELL':'Unknown'}))}/>
  </div>}
 </article>;
}

export default function AccountObservations({accounts,totals,onChanged}){
 return <section className="space-y-3" aria-label="Recorded broker account observations"><h2 className="font-semibold">MT5 account observations</h2><p className="text-xs muted">Read-only. Opening this page does not contact a broker. Refresh explicitly; recorded facts survive backend/browser restarts.</p>
  {totals?.map(g=><p className="text-sm" key={`${g.environment}:${g.currency}`}>{g.environment.toUpperCase()} · {g.currency} · {g.accounts} distinct accounts · Recorded balance {money(g.balance,g.currency)} · Equity {money(g.equity,g.currency)} · Observation window {g.oldest_observed_at} — {g.newest_observed_at}</p>)}
  {!accounts.length&&<p>No configured MT5 profiles.</p>}
  {accounts.map(a=><AccountCard key={`${a.profile_id}:${a.environment}:${a.account_key}`} account={a} onChanged={onChanged}/>)}
 </section>;
}
