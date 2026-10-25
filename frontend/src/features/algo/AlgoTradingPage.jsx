import {useEffect,useState} from 'react';
import {api} from '../../api/client';
import DataTable from '../../components/table/DataTable';
import RecoveryActivity from './RecoveryActivity';
import AccountSafeguards from './AccountSafeguards';
import DiagnosticWorkers from './DiagnosticWorkers';
import AccountObservations from './AccountObservations';
import DeploymentDraftForm from './DeploymentDraftForm';

const columns=[['name','Strategy','text'],['mode','Mode','category'],['environment','Environment','category'],['symbol','Symbol','text'],['status','Observed status','category'],['last_evaluation_at','Last evaluation','date']].map(([key,label,kind])=>({key,label,kind,render:row=>row[key]??'Unavailable'}));
const money=(value,currency)=>value==null?'Unavailable':`${Number(value).toFixed(2)} ${currency}`;
export default function AlgoTradingPage(){
 const [report,setReport]=useState(null),[error,setError]=useState(''),[selected,setSelected]=useState(null),[refresh,setRefresh]=useState(0);
 useEffect(()=>{let alive=true,timer;
  const load=async()=>{try{const result=await api.algoMonitoring();if(alive){setReport(result);setError('');}}
   catch(e){if(alive)setError(e.message);}finally{if(alive)timer=setTimeout(load,15000);}};
  load();return()=>{alive=false;clearTimeout(timer);};
 },[refresh]);
 const detail=report?.items.find(row=>row.id===selected);
 return <section className="space-y-4 min-w-0" aria-label="Algo Trading monitoring">
  <header className="ui-toolbar"><div><h1 className="text-2xl font-semibold">Algo Trading</h1><p className="text-sm muted">Execution readiness and recorded forward activity</p></div><button className="mini-btn" onClick={()=>setRefresh(n=>n+1)}>Refresh monitoring</button></header>
  <p className="text-sm">MT5 automated execution disabled. T01 is not deployed. This page does not start strategies or send orders.</p>
  <DeploymentDraftForm/>
  {error&&<p role="alert">{error}. {report?'Displayed data may be stale.':'No monitoring report received.'} Retrying automatically.</p>}
  {!report&&!error&&<p role="status">Loading monitoring state…</p>}
  {report&&<><p className="text-xs muted">Report refreshed {report.observed_at}. Broker observations and evaluations have their own timestamps.</p>
   <p className="text-xs muted">{report.limitation}</p>
   {report.warnings.map(w=><p role="status" key={w}>{w}</p>)}
   <AccountObservations accounts={report.accounts} totals={report.broker_totals} onChanged={()=>setRefresh(n=>n+1)}/>
   <DataTable id="algo.deployments" label="Strategy monitoring" columns={columns} rows={report.items} primaryAction={{label:'Inspect',onClick:row=>setSelected(row.id)}} summary={rows=><p className="p-3 text-xs muted">N = {rows.length} matching preparations/deployments. Simulated accounts are not pooled with broker balances.</p>}/>
   {!report.items.length&&<p className="text-sm muted">No recorded deployment or MT5 preparation. No sample performance is displayed.</p>}
   <DiagnosticWorkers rows={report.diagnostic_workers??[]}/>
   <RecoveryActivity key={selected??'all'} policyId={selected}/>
   {detail&&<article className="insight-panel" aria-label="Strategy monitoring detail"><div className="ui-toolbar"><h2 className="font-semibold">{detail.name}</h2><button className="mini-btn" onClick={()=>setSelected(null)}>Close details</button></div>
    <p>{detail.mode} · {detail.environment} · {detail.status}</p><p className="text-xs muted">{detail.limitation}</p>
    <p className="text-xs muted break-all">Identity {detail.id} · Source/definition {detail.source_hash}</p>
    <p>Last evaluation: {detail.last_evaluation_at??'Not observed'} · Saved state: {detail.persisted_status}</p>
    {detail.metrics&&<div className="grid gap-3 mt-3 sm:grid-cols-3"><p>Trades N={detail.metrics.n}{detail.metrics.low_sample?' · Low sample':''}</p><p>Average R: {detail.metrics.average_r?.toFixed(3)??'Unavailable'}</p><p>Win rate: {detail.metrics.win_rate_pct?.toFixed(1)??'Unavailable'}%</p><p>Simulated equity: {money(detail.equity,detail.currency)}</p><p>Max simulated drawdown: {money(detail.metrics.max_drawdown_cash,detail.currency)}</p><p>Profit factor: {detail.metrics.profit_factor?.toFixed(2)??'Unavailable'}</p></div>}
    <AccountSafeguards evidence={detail.safeguards} currency={detail.currency}/>
    <details className="mt-3"><summary>Recorded position and risk settings</summary><pre className="text-xs whitespace-pre-wrap break-all max-h-80 overflow-auto">{JSON.stringify({position:detail.position,risk:detail.risk,intent_counts:detail.intent_counts},null,2)}</pre></details>
    <details className="mt-3"><summary>Latest recorded trades (up to 100)</summary><pre className="text-xs whitespace-pre-wrap break-all max-h-80 overflow-auto">{JSON.stringify(detail.trades,null,2)}</pre></details>
    <p className="text-xs muted mt-3">Start, resume, stop and close-position controls are unavailable here until execution/protection/recovery integration is verified.</p>
   </article>}
  </>}
 </section>;
}
