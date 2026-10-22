// Opt-in production UI smoke. All API responses are fixtures; no real campaign writes.
import assert from 'node:assert/strict';
const base=process.env.LEDGER_SMOKE_URL;
assert(base&&new URL(base).hostname==='127.0.0.1');
const {send,evaluate,waitFor,click,errors,close}=await import('./cdp.mjs');
function fixtures(){
 localStorage.clear();localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Backtest'));
 const campaign={id:'fixture',status:'DEVELOPMENT_COMPLETE',created_at:'2026-10-21',request:{prompt:'Fixture failed baseline'},reserved:{llm_usd:1.89,simulations:40},execution:{entries:[]}};
 const report={campaign,worker:{running:true},summary:{baseline_runs_completed:0,numeric_cycles_completed:0,structural_checks_completed:0,holdout_consumed_by_campaign:false},morning_report:{families:[],conclusions:[]},events:[],progress:{outcome:'FAILED',counts:{queued:0,running:0,completed:0,failed:0,cancelled:1},family_failures:[{family_id:'selected_strategy',reason:'baseline_compute_deadline'}],jobs:[{id:'fixture-job',family_id:'selected_strategy',role:'baseline',status:'cancelled',processed:209408,total:790767,bar_progress_percent:26.4816,updated_at:'2026-10-21 17:52:15',suspected_stall:false}],eta_reason:'Dynamic work; reservations are not completed tasks.'}};
 window.progressRequests=[];
 report.operations={limitation:'Fixture metering only',model_operations:[{id:'model-fixture',family_id:'family',kind:'COMMITTEE',status:'FAILED',operation:{role:'Researcher',status:'RETURNED'},elapsed_seconds:12,reserved_calls:3,returned_usage_calls:1,reserved_cost_microusd:500000,estimated_reported_cost_microusd:100000,unpriced_returned_calls:0}]};
 report.operations.sandbox_operations=[{id:'docker-fixture',family_id:'family',status:'RUNNING',phase:'CAUSALITY_PREFIX',updated_at:'2026-10-21T17:52:15Z',suspected_stall:true,progress:{processed:25,total:100},lifecycle:[]}];
 report.activity={items:[{id:3,action:'FIXTURE_LATEST',created_at:'2026-10-21T17:52:15Z',detail:'Latest fixture'}],next_before:3};
 window.failOlder=true;
 window.fetch=async(url,options={})=>{
  const path=new URL(String(url),location.href).pathname;window.progressRequests.push({path,method:options.method||'GET'});
  let data={items:[]};
  if(path.endsWith('/research-campaigns/fixture/activity')){
   if(window.failOlder){window.failOlder=false;return new Response(JSON.stringify({detail:'Fixture temporary outage'}),{status:503,headers:{'Content-Type':'application/json'}});}
   data={items:[{id:2,action:'FIXTURE_OLDER',created_at:'2026-10-21T17:50:00Z',detail:'Older fixture'}],next_before:null};
  }
  else if(path.endsWith('/research-campaigns/policy'))data={presets:{},defaults:{}};
  else if(path.endsWith('/research-campaigns/fixture'))data=report;
  else if(path.endsWith('/research-campaigns'))data={items:[campaign]};
  else if(path.endsWith('/strategies'))data={strategies:[]};
  else if(path.endsWith('/runs'))data={runs:[]};
  else if(path.endsWith('/jobs'))data={jobs:[],compute:{mode:'1',configured_budget:1,used_workers:0}};
  else if(path.endsWith('/indicators'))data={indicators:[]};
  return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
 };
}
await send('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixtures.toString()})()`});
await send('Page.navigate',{url:base+'/?campaign-progress-smoke'});
await waitFor(`document.body.innerText.includes('Research Agent')`);
await click('Research Agent');
await waitFor(`document.body.innerText.includes('Recorded execution: FAILED')`);
assert(await evaluate(`document.body.innerText.includes('26.5%')&&document.body.innerText.includes('baseline_compute_deadline')&&document.body.innerText.includes('ETA unavailable')`));
assert(await evaluate(`!progressRequests.some(r=>r.method!=='GET')`));
assert(await evaluate(`document.querySelector('[aria-label="Recorded model operations"]').innerText.includes('Calls reserved: 3')&&document.querySelector('[aria-label="Recorded model operations"]').innerText.includes('Returned usage: 1')`));
assert(await evaluate(`document.querySelector('[aria-label="Recorded Docker operations"]').innerText.includes('25 / 100 bars observed')&&document.body.innerText.includes('Possible stall')`));
await click('Load older activity');
await waitFor(`document.querySelector('[aria-label="Campaign activity"] [role="alert"]')`);
assert(await evaluate(`document.body.innerText.includes('FIXTURE LATEST')`));
await click('Load older activity');
await waitFor(`document.body.innerText.includes('FIXTURE OLDER')`);
assert(await evaluate(`!document.body.innerText.includes('FIXTURE LATEST')`));
await click('Latest activity');
await waitFor(`document.body.innerText.includes('FIXTURE LATEST')`);
for(const width of [390,1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
 assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Page overflow '+width);
}
await send('Page.reload');
await waitFor(`document.body.innerText.includes('Research Agent')`);
if(!await evaluate(`document.body.innerText.includes('Recorded execution: FAILED')`))await click('Research Agent');
await waitFor(`document.body.innerText.includes('Recorded execution: FAILED')`);
assert.deepEqual(errors,[]);
console.log('Campaign progress production smoke passed: 390/1024/1440/1920; reload; GET-only; no runtime errors.');
await send('Browser.close');close();
