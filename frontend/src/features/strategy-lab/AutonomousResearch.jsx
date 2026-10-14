import {useEffect,useRef,useState} from 'react';
import {api} from '../../api/client';
import {campaignActions,campaignIsRunning,campaignPayload} from './campaignView.js';

const number=value=>value==null?'Unavailable':Number(value).toFixed(2);
const defaults={mode:'FIND_STRATEGIES',prompt:'',strategy_key:'',symbols:'QQQ',timeframe:'1m',history:'cached',
 model:false,structural:false,structural_cycles:1,numeric_cycles:1,starting_balance:10000,risk_value:1,
 commission_per_order:0,spread_bps:0,slippage_bps:0,max_leverage:1};

export default function AutonomousResearch({strategies}){
 const [form,setForm]=useState(defaults),[intensity,setIntensity]=useState('STANDARD'),[policies,setPolicies]=useState(null);
 const [items,setItems]=useState([]),[selected,setSelected]=useState(''),[report,setReport]=useState(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[consent,setConsent]=useState(false);
 const key=useRef(null),pending=useRef(null);
 const field=(name,value)=>{setForm(current=>({...current,[name]:value}));setConsent(false);};
 useEffect(()=>{let alive=true;Promise.all([api.researchCampaignPolicy(),api.researchCampaigns()]).then(([p,r])=>{
  if(alive){setPolicies(p);setItems(r.items);setSelected(r.items[0]?.id||'');}
 }).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[]);
 useEffect(()=>{if(!selected)return;let alive=true,timer;
  const poll=async()=>{try{const result=await api.researchCampaign(selected);if(!alive)return;setReport(result);
   if(campaignIsRunning(result.campaign.status))timer=setTimeout(poll,2500);
  }catch(e){if(alive)setError(e.message);}};
  setReport(null);poll();return()=>{alive=false;clearTimeout(timer);};
 },[selected,busy]);
 const launch=async()=>{setBusy(true);setError('');try{
  key.current ||= crypto.randomUUID();
  pending.current ||= campaignPayload(form,policies.presets[intensity],key.current);
  const item=await api.launchResearchCampaign(pending.current);
  setSelected(item.id);setItems(current=>[item,...current.filter(c=>c.id!==item.id)]);
  key.current=null;pending.current=null;setConsent(false);
 }catch(e){setError(e.message);if(e.status>=400&&e.status<500){pending.current=null;key.current=null;}}finally{setBusy(false);}};
 const control=async action=>{setBusy(true);setError('');try{await api.controlResearchCampaign(selected,action);}catch(e){setError(e.message);}finally{setBusy(false);}};
 const policy=policies?.presets[intensity],campaign=report?.campaign;
 return <section className="mt-5 space-y-4 min-w-0" aria-label="Autonomous research campaigns">
  <header><h3 className="text-xl font-semibold">Research campaigns</h3><p className="text-sm muted mt-2">Prepare chronological data, run registered strategy families and inspect development evidence. The backend continues after you close this page. Nothing is deployed or traded.</p></header>
  {error&&<p role="alert">{error}</p>}
  <details className="insight-panel" open={!selected}><summary>Start a bounded campaign</summary>
   <fieldset disabled={busy||Boolean(pending.current)} className="mt-3 space-y-3">
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
     <label>Goal<select className="input" value={form.mode} onChange={e=>field('mode',e.target.value)}><option value="FIND_STRATEGIES">Find strategies</option><option value="IMPROVE_STRATEGY">Improve a strategy</option></select></label>
     {form.mode==='IMPROVE_STRATEGY'&&<label>Strategy<select className="input" value={form.strategy_key} onChange={e=>field('strategy_key',e.target.value)}><option value="">Select strategy</option>{strategies.map(s=><option key={s.key} value={s.key}>{s.name}</option>)}</select></label>}
     <label>Symbols<input className="input" value={form.symbols} onChange={e=>field('symbols',e.target.value)}/></label>
     <label>Primary bars<select className="input" value={form.timeframe} onChange={e=>field('timeframe',e.target.value)}>{['1m','5m','15m','30m','1h'].map(tf=><option key={tf}>{tf}</option>)}</select></label>
     <label>Budget preset<select className="input" value={intensity} onChange={e=>{setIntensity(e.target.value);setConsent(false);}}>{['QUICK','STANDARD','DEEP'].map(p=><option key={p}>{p}</option>)}</select></label>
     <label>History<select className="input" value={form.history} onChange={e=>field('history',e.target.value)}><option value="cached">Use cached history</option><option value="provider">Prepare provider history</option></select></label>
    </div>
    <label className="block">Research objective (optional)<textarea className="input" maxLength={4000} value={form.prompt} onChange={e=>field('prompt',e.target.value)}/></label>
    <p className="text-xs muted">Find strategies uses the registered research catalog in fixed order. Novel strategy synthesis and literature search are not available. Automatic history planning currently supports US equities.</p>
    <details open><summary>Account and costs — confirm before starting</summary><div className="grid gap-3 mt-3 sm:grid-cols-3">{[['starting_balance','Starting balance'],['risk_value','Risk per trade (%)'],['max_leverage','Maximum leverage'],['commission_per_order','Commission per order'],['spread_bps','Spread (bps)'],['slippage_bps','Slippage (bps)']].map(([name,label])=><label key={name}>{label}<input className="input" type="number" min="0" step="any" value={form[name]} onChange={e=>field(name,e.target.value)}/></label>)}</div><p className="text-xs muted mt-2">Zero costs mean frictionless research. Enter realistic costs. Every family has independent capital; results are not a portfolio.</p></details>
    <label className="block"><input type="checkbox" checked={form.model} onChange={e=>field('model',e.target.checked)}/> Allow paid model review of development evidence</label>
{form.model&&<><label className="block">Numeric cycles per family<select className="input" value={form.numeric_cycles} onChange={e=>field('numeric_cycles',e.target.value)}>{[0,1,2].map(n=><option key={n}>{n}</option>)}</select></label><label className="block"><input type="checkbox" checked={form.structural} onChange={e=>field('structural',e.target.checked)}/> Allow structural research: send archived source to the model and test only in Docker</label>{form.structural&&<label className="block">Maximum structural attempts per family<select className="input" value={form.structural_cycles} onChange={e=>field('structural_cycles',e.target.value)}>{[1,2,3].map(n=><option key={n}>{n}</option>)}</select></label>}<p className="text-xs muted">New campaigns evaluate children across the planned development period with historical warmup, control parity and causality checks. Cost checks cover complete preregistered development windows at original and doubled costs, with independently reset accounts; these are not unseen validation. Execution stays within reserved time and memory limits. A single attempt requires at least 30 simulations per family with three windows; additional attempts reserve more budget before starting. Rejected or insufficient evidence may lead to a distinct hypothesis, never an automatic repeat of identical code. Model pricing must be configured. Failed/interrupted calls retain their cost reservation.</p></>}
    {policy&&<p className="text-sm">Ceilings: {policy.budget.wall_minutes} wall minutes · {policy.budget.simulations} simulations · {policy.budget.llm_calls} model calls · ${policy.budget.llm_usd} reserved model cost. Preparation shares the time budget.</p>}
    <label className="block"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/> I authorize these settings, costs and selected permissions. Holdout remains locked.</label>
   </fieldset>
   <button className="mini-btn mt-3" disabled={busy||!policies||!consent} onClick={launch}>{busy?'Starting…':pending.current?'Retry same launch':'Start campaign'}</button>
   {pending.current&&<p className="text-xs muted mt-2">The pending request is frozen to prevent duplicate paid work. Retry preserves its identity.</p>}
  </details>
  <label className="block">Campaign<select className="input" value={selected} onChange={e=>setSelected(e.target.value)}><option value="">Select campaign</option>{items.map(c=><option key={c.id} value={c.id}>{c.request.prompt||c.request.mode} · {c.created_at}</option>)}</select></label>
  {campaign&&<><article className="insight-panel"><h4 className="font-semibold">{campaign.status.replaceAll('_',' ')}</h4>
   <p className="text-sm muted mt-2">{report.worker.running?'Backend coordinator running':'Backend coordinator is not running'}{report.worker.error?' · '+report.worker.error:''}</p>
   {campaign.last_error&&<p role="alert">{campaign.last_error}. Check history coverage, model configuration, Docker and budget allowances before creating a new campaign.</p>}
   <div className="ui-toolbar mt-3">{campaignActions(campaign.status).map(action=><button className="mini-btn" disabled={busy} key={action} onClick={()=>control(action)}>{action.replaceAll('_',' ')}</button>)}</div>
   <p className="text-sm mt-3">Baselines: {report.summary.baseline_runs_completed} · Numeric cycles: {report.summary.numeric_cycles_completed} · Structural checks: {report.summary.structural_checks_completed}</p>
   <p className="text-xs muted">Model reservation ${number(campaign.reserved.llm_usd)} · Simulations reserved {campaign.reserved.simulations} · Holdout {report.summary.holdout_consumed_by_campaign?'consumed':'not consumed'}</p>
   {campaign.preparation&&<p className="text-sm mt-2">History preparation: {campaign.preparation.status} · Fixed deadline {campaign.preparation.deadline}</p>}
  </article>
  <article className="insight-panel"><h4 className="font-semibold">Research report</h4><div className="overflow-x-auto mt-3"><table className="w-full text-sm text-left"><thead><tr>{['Family','Progress','Baseline N','Baseline avg R','Child N','Finding'].map(h=><th className="p-2 whitespace-nowrap" key={h}>{h}</th>)}</tr></thead><tbody>{report.morning_report.families.map(f=><tr key={f.project_id}><td className="p-2">{f.family_id}</td><td className="p-2">{f.state}</td><td className="p-2">{f.baseline_summary?.n??'—'}</td><td className="p-2">{number(f.baseline_summary?.average_r)}</td><td className="p-2">{f.child_summary?.n??'—'}</td><td className="p-2">{f.verdict}{f.reason&&<p>{f.reason}</p>}{f.warnings.map(w=><p key={w} className="muted mt-1">{w}</p>)}</td></tr>)}</tbody></table></div>
   {report.morning_report.conclusions.map(t=><p className="text-xs muted mt-2" key={t}>{t}</p>)}
   {report.morning_report.families.filter(f=>f.robustness?.cells?.length).map(f=><details className="mt-3" key={f.project_id}><summary>{f.family_id}: development windows and cost checks</summary><p className="text-xs muted mt-2">Independent accounts per sample. Do not sum these returns into portfolio performance. Dates were fixed before results.</p><div className="overflow-x-auto"><table className="w-full text-sm text-left" aria-label={`${f.family_id} robustness samples`}><thead><tr>{['Window','Dates','Costs','Status','N','Avg R','Total R','PF (R)'].map(h=><th key={h} className="p-2 whitespace-nowrap">{h}</th>)}</tr></thead><tbody>{f.robustness.cells.map(c=><tr key={`${c.window}-${c.cost_multiplier}`}><td className="p-2">{c.window}</td><td className="p-2 whitespace-nowrap">{c.start} to {c.end}</td><td className="p-2">{c.cost_multiplier}×</td><td className="p-2">{c.status}</td><td className="p-2">{c.summary?.n??'Unavailable'}</td><td className="p-2">{number(c.summary?.average_r)}</td><td className="p-2">{number(c.summary?.total_r)}</td><td className="p-2">{number(c.summary?.profit_factor_r)}</td></tr>)}</tbody></table></div></details>)}
   {report.morning_report.families.filter(f=>f.research_decision).map(f=><div className="mt-3" key={f.project_id}><h5 className="font-semibold">{f.family_id}: {f.research_decision.verdict.replaceAll('_',' ')}</h5><p className="text-xs muted">{f.structural_attempts?.length??0} completed structural attempts. {f.research_decision.limitation}</p>{f.research_decision.reasons.map(reason=><p className="text-sm" key={reason}>{reason}</p>)}</div>)}
   <details className="mt-3"><summary>Source identity, winner retention and evidence</summary><pre className="text-xs max-h-96 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify(report.morning_report,null,2)}</pre></details>
   <details className="mt-3"><summary>Frozen plan, budgets and audit history</summary><pre className="text-xs max-h-96 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify({plans:campaign.plans,execution:campaign.execution,reserved:campaign.reserved,events:report.events},null,2)}</pre></details>
  </article></>}
 </section>;
}
