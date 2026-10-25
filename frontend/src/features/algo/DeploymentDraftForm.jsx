import {useEffect,useState} from 'react';
import {api} from '../../api/client';

export default function DeploymentDraftForm({runId,strategyKey='gold_ifvg_v2_fvg_ratio_020'}){
 const [open,setOpen]=useState(false);
 return <section className="insight-panel"><button className="mini-btn" onClick={()=>setOpen(v=>!v)}>{open?'Close deployment configuration':'Deploy to DEMO'}</button><p className="text-xs muted">Configure an unarmed saved-run draft. Activation is unavailable until DEMO execution acceptance passes.</p>{open&&<Draft runId={runId} strategyKey={strategyKey}/>}</section>;
}
function Draft({runId,strategyKey}){
 const [form,setForm]=useState({request_key:crypto.randomUUID(),run_id:runId??'',strategy_key:strategyKey,name:strategyKey==='gold_ifvg_v2_fvg_ratio_020'?'Gold T02 DEMO':'Gold T01 DEMO',profile_id:'',broker_symbol:'',mode:'DEMO',risk_percent:.5,max_daily_loss_percent:2,max_positions:1,max_trades_per_day:1,max_gross_exposure:''});
 const [profiles,setProfiles]=useState([]),[token,setToken]=useState(''),[preview,setPreview]=useState(null),[saved,setSaved]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{let alive=true;api.brokerProfiles().then(r=>{if(alive)setProfiles(r.items.filter(p=>p.provider==='mt5'&&p.environment==='demo'&&p.configured&&p.account_key))}).catch(e=>{if(alive)setError(e.message)});return()=>{alive=false}},[]);
 function change(key,value){setForm(old=>({...old,[key]:value,request_key:crypto.randomUUID()}));setPreview(null);setSaved(null);}
 async function submit(save){setBusy(true);setError('');try{const result=await api.mt5DeploymentDraft({...form,run_id:Number(form.run_id)},token,!save);if(save)setSaved(result);else setPreview(result);}catch(e){setError(e.message)}finally{setBusy(false)}}
 return <div className="space-y-3 mt-3" aria-label="DEMO deployment configuration">
  <p className="text-xs muted">T01/T02 only at this stage. Source mismatch blocks preparation. Saved results are never edited. Only direction is configurable; 1R, +0.68R and the variant&apos;s rules stay frozen.</p>
  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
   <label>Strategy<select className="input" value={form.strategy_key} disabled={!!runId||busy} onChange={e=>change('strategy_key',e.target.value)}><option value="gold_ifvg_v2_fvg_ratio_020">Gold T02 · FVG/stop ≤ 0.20</option><option value="gold_ifvg_v2_skip_23et">Gold T01 · skip 23 ET</option></select></label>
   <label>Saved run ID<input className="input" type="number" min="1" value={form.run_id} disabled={!!runId||busy} onChange={e=>change('run_id',e.target.value)}/></label>
   <label>Deployment name<input className="input" value={form.name} maxLength={100} disabled={busy} onChange={e=>change('name',e.target.value)}/></label>
   <label>Verified DEMO profile<select className="input" value={form.profile_id} disabled={busy} onChange={e=>change('profile_id',e.target.value)}><option value="">Select account</option>{profiles.map(p=><option key={p.profile_id} value={p.profile_id}>{p.profile_id} · {p.account_key.slice(0,12)}</option>)}</select></label>
   <label>Exact discovered Gold broker symbol<input className="input" value={form.broker_symbol} disabled={busy} onChange={e=>change('broker_symbol',e.target.value)}/></label>
   <label>Requested mode<select className="input" value={form.mode} disabled={busy} onChange={e=>change('mode',e.target.value)}><option>DEMO</option><option>SHADOW</option></select></label>
   <label>Direction<select className="input" value={form.direction??''} disabled={busy} onChange={e=>change('direction',e.target.value||null)}><option value="">Inherit saved run</option><option value="both">Both</option><option value="long">Long</option><option value="short">Short</option></select></label>
   {[['risk_percent','Target risk %'],['max_daily_loss_percent','Daily loss limit % · UTC day'],['max_positions','Maximum positions'],['max_trades_per_day','Maximum trades/day'],['max_gross_exposure','Maximum account gross exposure · account currency']].map(([key,label])=><label key={key}>{label}<input className="input" type="number" min="0" step={key.includes('percent')?'.1':'1'} value={form[key]} disabled={busy} onChange={e=>change(key,e.target.value===''?'':Number(e.target.value))}/></label>)}
  </div>
  <p className="text-xs muted">Session remains 20:00–00:00 America/New_York, including DST. Limits must include external/manual/Telegram activity. These draft limits are not active protections.</p>
  <label>Deployment operator token<input className="input" type="password" autoComplete="off" value={token} onChange={e=>setToken(e.target.value)}/></label>
  <p className="text-xs muted">Backend MT5_ALGO_CONTROL_TOKEN; memory only, cleared when this form closes. Remote controls require HTTPS.</p>
  <button className="mini-btn" disabled={busy||token.length<32} onClick={()=>submit(false)}>{busy?'Validating…':'Validate draft'}</button>
  {preview&&<div className="space-y-2"><p>Recorded-equity target risk estimate: {preview.estimated_target_risk?.toFixed(2)} {preview.estimate_currency} · observed {preview.estimate_observed_at}</p><p className="text-xs break-all">Strategy {preview.definition.strategy_key} · source SHA-256 {preview.definition.implementation.source_sha256}</p><p>{preview.warning}</p><p>Activation blockers: {preview.blockers.join(' · ')}</p><button className="mini-btn" disabled={busy||!!saved} onClick={()=>submit(true)}>Save unarmed draft</button></div>}
  {saved&&<p role="status">Saved {saved.id} · {saved.state}. No worker started; no orders authorized.</p>}
  {error&&<p role="alert">{error}</p>}
 </div>;
}
