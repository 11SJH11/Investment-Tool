import {useEffect,useRef,useState} from 'react';
import {api} from '../../api/client';
import PaperValidation from './PaperValidation';
import ForwardComparison from './ForwardComparison';

const fields=[['starting_balance','Independent starting balance'],['risk_value','Shadow risk per trade (%)'],['commission_per_order','Commission per order'],['spread_bps','Spread (bps)'],['slippage_bps','Slippage (bps)']];
export default function ForwardValidation(){
 const [report,setReport]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [account,setAccount]=useState({starting_balance:10000,risk_value:1,commission_per_order:0,spread_bps:0,slippage_bps:0});
 const [consent,setConsent]=useState(false);const pending=useRef(null);
 useEffect(()=>{let alive=true,timer;const poll=async()=>{try{const data=await api.forwardReport();if(alive)setReport(data);}catch(e){if(alive)setError(e.message);}finally{if(alive)timer=setTimeout(poll,5000);}};poll();return()=>{alive=false;clearTimeout(timer);};},[]);
 async function prepare(){setBusy(true);setError('');try{
  pending.current ||= {request_key:crypto.randomUUID(),account:Object.fromEntries(Object.entries(account).map(([k,v])=>[k,Number(v)])),acknowledgement:'Start four independent IEX shadows; no broker orders'};
  await api.forwardPrepare(pending.current);pending.current=null;setConsent(false);setReport(await api.forwardReport());
 }catch(e){setError(e.message);if(e.status>=400&&e.status<500)pending.current=null;}finally{setBusy(false);}}
 async function halt(id){setBusy(true);try{await api.forwardHalt(id);setReport(await api.forwardReport());}catch(e){setError(e.message);}finally{setBusy(false);}}
 return <section className="mt-5 space-y-4 min-w-0" aria-label="Forward validation"><header><h3 className="text-xl font-semibold">Forward validation</h3><p className="text-sm muted mt-2">Four independent Baseline/B/C/D shadows using frozen D6 rules. IEX raw warmup and incoming minutes share one feed. The backend continues after this page closes.</p></header>
 {error&&<p role="alert">{error}</p>}
 <details className="insight-panel"><summary>Start an IEX shadow experiment</summary><p className="text-xs muted mt-2">IEX covers one exchange, not consolidated SIP volume. Missing or revised minutes halt the experiment. Sixty complete sessions are required for warmup; preparation may fail if IEX coverage is incomplete. No synthetic bars or paper orders. Each shadow has its own capital; returns are not a portfolio.</p>
 <fieldset disabled={busy||Boolean(pending.current)} className="grid gap-3 sm:grid-cols-3 mt-3">{fields.map(([key,label])=><label key={key}>{label}<input className="input" type="number" min={['starting_balance','risk_value'].includes(key)?0.01:0} step="any" value={account[key]} onChange={e=>{setAccount({...account,[key]:e.target.value});setConsent(false);}}/></label>)}</fieldset>
 <p className="text-xs muted mt-2">Confirm realistic costs. Zero costs mean frictionless shadow research. These are shadow risk settings, not paper risk authorization.</p>
 <label className="block mt-3"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/> Prepare provider history and start these four shadows with the displayed assumptions.</label>
 <button className="mini-btn mt-3" disabled={busy||!report?.configured||!consent} onClick={prepare}>{busy?'Preparing request…':pending.current?'Retry same request':'Prepare and start shadows'}</button>{!report?.configured&&<p className="text-sm mt-2">Configure Alpaca credentials in Settings before preparing data.</p>}</details>
 {report?.items?.map(item=><article className="insight-panel" key={item.id}><div className="ui-toolbar"><h4 className="font-semibold">Experiment {item.id.slice(0,8)}</h4><span>{item.preparation?.status||'DRAFT'}</span><button className="mini-btn" disabled={busy} onClick={()=>halt(item.id)}>Stop shadows</button></div>{item.preparation?.error&&<p role="alert" className="mt-2">{item.preparation.error}</p>}
 <div className="overflow-x-auto mt-3"><table className="w-full text-sm text-left"><thead><tr>{['Deployment','Status','Equity','Trades','Entries today','Last decision','Position'].map(h=><th className="p-2 whitespace-nowrap" key={h}>{h}</th>)}</tr></thead><tbody>{item.deployments.map(d=><tr key={d.id}><th className="p-2 whitespace-nowrap">{d.name}</th><td className="p-2">{d.state.status}</td><td className="p-2">{Number(d.state.equity).toFixed(2)}</td><td className="p-2">{d.state.trade_count}</td><td className="p-2">{d.state.trades_today}</td><td className="p-2 whitespace-nowrap">{d.state.last_evaluated_decision_at||'Awaiting data'}</td><td className="p-2">{d.state.position?`${d.state.position.direction} ${d.state.position.quantity}`:'Flat'}</td></tr>)}</tbody></table></div>
 <ForwardComparison report={item.paper_comparison}/>
 <details className="mt-3"><summary>Frozen settings, source identities and latest 100 trades per shadow</summary><pre className="text-xs max-h-96 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify(item.deployments,null,2)}</pre></details></article>)}
 {!report?.items?.length&&<p className="text-sm muted">No forward experiment has been prepared.</p>}
 <p className="text-xs muted">Shadow fills are simulated engine fills. Paper execution requires separate controls and consent below.</p>
 <PaperValidation experiments={report?.items||[]}/>
 </section>;
}
