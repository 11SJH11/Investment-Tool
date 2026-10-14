// Opt-in browser acceptance with all network responses mocked before app load.
import assert from 'node:assert/strict';
const base=process.env.LEDGER_SMOKE_URL;
assert(base&&new URL(base).hostname==='127.0.0.1');
const {send,evaluate,waitFor,click,errors,close}=await import('./cdp.mjs');
errors.length=0;
function fixtures(){
 localStorage.clear();localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Backtest'));
 window.validationCalls=[];let grant=null;
 const project={id:'fixture',name:'Isolated validation',state:'BASELINE_ANALYSIS',strategy_key:'fixture',research_debt:{uses:0},datasets:[{id:'held',symbols:['QQQ'],timeframe:'1m',start:'2027-01-01',end:'2027-12-31',state:'LOCKED_HOLDOUT'}],analyses:{},lineage:[],events:[]};
 window.fetch=async(url,options={})=>{
  const p=new URL(String(url),location.href).pathname,method=options.method||'GET';validationCalls.push({p,method,body:options.body});let body={items:[]};
  if(p.endsWith('/strategies'))body={strategies:[{key:'fixture',name:'Fixture',defaults:{},parameters:[],supported_timeframes:['1m']}]};
  else if(p.endsWith('/indicators'))body={indicators:[]};
  else if(p.endsWith('/runs'))body={runs:[]};
  else if(p.endsWith('/jobs'))body={jobs:[],compute:{mode:'1',configured_budget:1,used_workers:0}};
  else if(p.endsWith('/research-campaigns/policy')){const policy={symbols:['QQQ'],timeframes:['1m'],directions:['long','short'],minimum_trades:30,holdout:'human_approval',budget:{wall_minutes:60,simulations:24,llm_calls:12,llm_usd:2},dataset:{}};body={defaults:policy,presets:{QUICK:policy,STANDARD:policy,DEEP:policy}};}
  else if(p.endsWith('/research-agent'))body={items:[project]};
  else if(p.endsWith('/research-agent/fixture'))body=project;
  else if(p.endsWith('/candidates'))body={items:[{id:'generated',kind:'GENERATED_DEVELOPMENT',state:'FROZEN_DEVELOPMENT',reason:'Verified development fixture',snapshot:{},snapshot_hash:'fixture'}]};
  else if(p.endsWith('/validations'))body={items:grant?[grant]:[]};
  else if(p.endsWith('/validate-isolated')){grant={id:'grant',candidate_id:'generated',kind:'GENERATED_ISOLATED',status:'ACTIVE',verdict:'PENDING'};project.datasets[0].state='INSPECTED_VALIDATION';body=grant;}
  else if(p.endsWith('/cancel-isolated')){grant.status='CANCELLED';body=grant;}
  else if(p.endsWith('/loop'))body=null;
  else if(p.endsWith('/committee'))body={items:[],model:{configured:false},reserved_calls:0,max_calls:0};
  else if(p.endsWith('/trials'))body={items:[],reserved_runs:0,budget:{max_trial_runs:24}};
  return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}});
 };
}
await send('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixtures.toString()})()`});
await send('Page.navigate',{url:base+'/?isolated-validation='+Date.now()});
await waitFor(`document.body.innerText.includes('Research Agent')`);await click('Research Agent');
await waitFor(`document.body.innerText.includes('Advanced projects')`);await click('Advanced projects');
await waitFor(`document.body.innerText.includes('Isolated validation / BASELINE_ANALYSIS')`);await click('Isolated validation / BASELINE_ANALYSIS');
await waitFor(`document.body.innerText.includes('Generated source / FROZEN_DEVELOPMENT')`);
await evaluate(`[...document.querySelectorAll('summary')].find(e=>e.textContent.includes('Generated source /')).click()`);
await waitFor(`document.body.innerText.includes('Candidate-specific validation')`);
assert(await evaluate(`document.body.innerText.includes('four isolated validation checks')`));
assert(await evaluate(`!validationCalls.some(c=>c.method==='POST')`));
await evaluate(`(()=>{const s=document.querySelector('[aria-label="Candidate validation dataset"]');s.value='held';s.dispatchEvent(new Event('change',{bubbles:true}));})()`);
assert(await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='Approve and run candidate validation').disabled`));
await evaluate(`[...document.querySelectorAll('label')].find(l=>l.textContent.includes('I approve consuming this dataset')).querySelector('input').click()`);
await click('Approve and run candidate validation');await waitFor(`document.body.innerText.includes('ACTIVE / PENDING')`);
assert(await evaluate(`validationCalls.filter(c=>c.p.endsWith('/validate-isolated')).length===1&&!validationCalls.some(c=>c.p.endsWith('/validate'))`));
await click('Cancel validation');await waitFor(`document.body.innerText.includes('CANCELLED / PENDING')`);
assert(await evaluate(`document.body.innerText.includes('INSPECTED_VALIDATION')`));
for(const width of [1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
 assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Page overflow '+width);
}
assert.equal(errors.length,0,errors.join('\n'));
console.log('PASS generated validation consent, isolated endpoint, polling, cancellation, inspected dataset, 1024/1440/1920 and runtime checks.');
close();
