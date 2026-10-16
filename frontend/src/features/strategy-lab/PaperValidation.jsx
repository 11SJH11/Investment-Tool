import {useEffect,useState} from 'react';
import {api} from '../../api/client';

export default function PaperValidation({experiments=[]}){
 const [report,setReport]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[consent,setConsent]=useState({});
 const [risk,setRisk]=useState({fixed_notional:'1000',max_equity_fraction:'0.1',max_daily_loss_percent:'2'});
 useEffect(()=>{let live=true,timer;const poll=async()=>{try{const value=await api.paperReport();if(live)setReport(value);}catch(e){if(live)setError(e.message);}finally{if(live)timer=setTimeout(poll,5000);}};poll();return()=>{live=false;clearTimeout(timer);};},[]);
 async function perform(operation){setBusy(true);setError('');try{setReport(await operation());setConsent({});}catch(e){setError(e.message);}finally{setBusy(false);}}
 const valid=Object.values(risk).every(v=>String(v).trim()!==''&&Number.isFinite(Number(v))&&Number(v)>0);
 return <section className="insight-panel space-y-3" aria-label="Alpaca paper execution">
 <div className="ui-toolbar"><h3 className="text-xl font-semibold">B · Alpaca paper</h3><button className="mini-btn" disabled={busy} onClick={()=>perform(()=>api.paperDisarmAll())}>Disarm all paper entries</button></div>
 <p className="text-sm">Paper only. Entry fills are followed by broker-held market-on-close protection. The interval before protection is confirmed, and cancellation/replacement intervals, are unprotected. Closing orders are not guaranteed fills.</p>
 <p className="text-xs muted">Use a dedicated paper account. Disarming stops new entries; existing closing protection remains monitored. Partial entries are cancelled before protecting their confirmed quantity. Near the auction cutoff, earlier exits defer to the broker-held close. Restart requires explicit re-arming.</p>
 {error&&<p role="alert">{error}</p>}
 <details><summary>Configure a separate B paper deployment</summary><fieldset disabled={busy} className="grid gap-3 sm:grid-cols-3 my-3">
 {[['fixed_notional','Maximum position notional ($)'],['max_equity_fraction','Maximum equity fraction (0–1)'],['max_daily_loss_percent','Daily loss limit (%)']].map(([key,label])=><label key={key}>{label}<input className="input" type="number" min="0.01" step="any" value={risk[key]} onChange={e=>setRisk({...risk,[key]:e.target.value})}/></label>)}</fieldset>
 {experiments.filter(e=>e.preparation?.status==='READY'&&!report?.items?.some(p=>p.experiment_id===e.id)).map(e=><button className="mini-btn" key={e.id} disabled={busy||!valid||!report?.configured} onClick={()=>perform(()=>api.paperPrepare({experiment_id:e.id,risk:Object.fromEntries(Object.entries(risk).map(([k,v])=>[k,Number(v)]))}))}>Configure B for {e.id.slice(0,8)}</button>)}
 <p className="text-xs muted">Configuration does not arm or submit orders. Prepare an IEX shadow experiment first. Risk is independent of shadow sizing.</p></details>
 {!report?.configured&&<p>Alpaca paper credentials are not configured.</p>}
 {report?.items?.map(item=><article key={item.id} className="space-y-2 border-t pt-3">
 <strong>{item.id.slice(0,8)} · {item.armed?'ARMED':'DISARMED'}</strong>
 <p>Position: {item.position_qty||'0'} QQQ · Protection: {item.close_protection?.status||'Not established'} · Last reconciliation: {item.reconciled_at||'Not connected'}</p>
 <p className="text-xs muted">Cap ${item.risk.fixed_notional} / {100*item.risk.max_equity_fraction}% equity; daily loss limit {item.risk.max_daily_loss_percent}%.</p>
 {item.last_error&&<p role="alert">{item.last_error}</p>}
 <label className="block"><input type="checkbox" checked={Boolean(consent[item.id])} onChange={e=>setConsent({...consent,[item.id]:e.target.checked})}/> I authorize B paper entries with these limits and accept the post-fill and cancellation/replacement protection gaps.</label>
 <div className="ui-toolbar"><button className="mini-btn" disabled={busy||!consent[item.id]||item.armed} onClick={()=>perform(()=>api.paperControl(item.id,{action:'arm',acknowledgement:report.acknowledgement}))}>Arm B paper</button>
 <button className="mini-btn" disabled={busy} onClick={()=>perform(()=>api.paperControl(item.id,{action:'disarm'}))}>Disarm entries</button>
 <button className="mini-btn" disabled={busy} onClick={()=>perform(()=>api.paperControl(item.id,{action:'cancel',acknowledgement:'cancel'}))}>Cancel open paper orders</button>
 <button className="mini-btn" disabled={busy} onClick={()=>perform(()=>api.paperControl(item.id,{action:'flatten',acknowledgement:'flatten'}))}>Request paper flatten</button></div>
 <p className="text-xs muted">Cancel removes open protection too and requires review before new entries. Flatten waits for confirmed cancellation and broker fills. Near the cutoff it retains the auction exit.</p>
 </article>)}
 </section>;
}
