// Opt-in production smoke. All observations below are explicitly mocked.
import assert from 'node:assert/strict';
const base=process.env.LEDGER_SMOKE_URL;
assert(base&&new URL(base).hostname==='127.0.0.1');
const {send,evaluate,waitFor,click,errors,close}=await import('./cdp.mjs');
function fixtures(){
 localStorage.clear();localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Algo Trading'));
 window.monitorRequests=[];window.failMonitor=false;window.failRecovery=true;window.failDecisions=true;
 const report={observed_at:'2026-10-22T12:00:00Z',accounts:[],warnings:[],limitation:'Fixture observations only',items:[{id:'fixture',name:'T01 preparation fixture',mode:'MT5_PREPARATION',environment:'demo',symbol:'XAUUSD',status:'NOT_DEPLOYED',persisted_status:'DISABLED',source_hash:'fixture-hash',metrics:null,trades:[],risk:{},limitation:'Saved policy only'}]};
 report.items[0].currency='USD';
 report.diagnostic_workers=[{id:'worker-fixture',stream_id:'worker-fixture',profile_id:'demo-fixture',state:'RECOVERY_REQUIRED',thread_alive:false,heartbeat_at:'2026-10-23T00:00:00Z',last_decision_at:null,error_category:'diagnostic_cycle_failed'}];
 report.items[0].safeguards={guard:{state:'RECONCILIATION_REQUIRED',since:'2026-10-23T00:00:00Z'},recorded_account_attempts:2,latest_risk_assessment:{allowed:false,reasons:['uncertain_submission'],evaluated_at_ms:1000000,risk_day_utc:'1970-01-01',projected_loss_budget:100,projected_gross_exposure:5000}};
 report.items[0].safeguards.latest_diagnostic_stream={id:'diagnostic-fixture',completed_decisions:60,last_decision_at:'2026-10-23T01:00:00Z',last_signal:'entry',mode:'DIAGNOSTIC_ONLY'};
 report.recovery_observations=[{id:'recovery',policy_id:'fixture',intent_id:'intent',observed_at_ms:1000000,state:'PROTECTION_UNVERIFIED',identity_basis:'durable_attempt_receipt',complete:true,filled_lots:'0.1',remaining_lots:'0.1'}];
 window.fetch=async(url,options={})=>{
  const parsed=new URL(String(url),location.href),path=parsed.pathname;window.monitorRequests.push({path,query:parsed.search,method:options.method||'GET'});
  if(path.endsWith('/algo-trading/diagnostic-decisions')){
   if(parsed.searchParams.has('before')&&window.failDecisions){window.failDecisions=false;return new Response(JSON.stringify({detail:'Fixture decisions outage'}),{status:503,headers:{'Content-Type':'application/json'}});}
   const older=parsed.searchParams.has('before');
   return new Response(JSON.stringify({items:[{id:older?'older-decision':'latest-decision',sequence:older?1:2,decision_kind:older?'no_signal':'entry',direction:'short',integrity:'checksum_verified',stop_loss:3010,target_r:1}],next_before:older?null:2}),{headers:{'Content-Type':'application/json'}});
  }
  if(path.endsWith('/algo-trading/recovery')){
   if(parsed.searchParams.has('before')&&window.failRecovery){window.failRecovery=false;return new Response(JSON.stringify({detail:'Fixture recovery outage'}),{status:503,headers:{'Content-Type':'application/json'}});}
   const data=parsed.searchParams.has('before')?{items:[{...report.recovery_observations[0],id:'older',state:'OLDER_UNRESOLVED'}],next_before:null}:{items:report.recovery_observations,next_before:99};
   return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
  }
  if(path.endsWith('/algo-trading')&&window.failMonitor)return new Response(JSON.stringify({detail:'Fixture outage'}),{status:503,headers:{'Content-Type':'application/json'}});
  const data=path.endsWith('/algo-trading')?report:path.endsWith('/jobs')?{jobs:[],compute:{mode:'1',configured_budget:1,used_workers:0}}:{items:[]};
  return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
 };
}
await send('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixtures.toString()})()`});
await send('Page.navigate',{url:base+'/?algo-monitoring-smoke'});
await waitFor(`document.body.innerText.includes('NOT_DEPLOYED')`);
assert(await evaluate(`document.querySelector('[aria-label="Read-only diagnostic workers"]').innerText.includes('RECOVERY_REQUIRED')`));
assert(await evaluate(`document.body.innerText.includes('never resumes them automatically after restart')`));
await click('View decisions');
await waitFor(`document.querySelector('[aria-label="Recorded diagnostic decisions"]').innerText.includes('checksum_verified')`);
assert(await evaluate(`document.body.innerText.includes('suggestions are not orders')`));
await click('Older diagnostic decisions');
await waitFor(`document.body.innerText.includes('Previous decisions retained')`);
assert(await evaluate(`document.querySelector('[aria-label="Recorded diagnostic decisions"]').innerText.includes('3010')`));
await click('Older diagnostic decisions');
await waitFor(`document.querySelector('[aria-label="Recorded diagnostic decisions"]').innerText.includes('no_signal')`);
await click('Latest diagnostic decisions');
await waitFor(`document.querySelector('[aria-label="Recorded diagnostic decisions"]').innerText.includes('entry')`);
await waitFor(`document.body.innerText.includes('PROTECTION_UNVERIFIED')`);
assert(await evaluate(`document.body.innerText.includes('Protection evidence may be stale')`));
await click('Inspect');
await waitFor(`document.querySelector('[aria-label="Strategy monitoring detail"]')`);
assert(await evaluate(`document.querySelector('[aria-label="Persisted account safeguards"]').innerText.includes('RECONCILIATION_REQUIRED')`));
assert(await evaluate(`document.body.innerText.includes('uncertain submission') && document.body.innerText.includes('100 USD')`));
assert(await evaluate(`document.body.innerText.includes('not current risk consumption or permission to trade')`));
assert(await evaluate(`document.body.innerText.includes('Completed decisions: 60') && document.body.innerText.includes('not trades, a worker heartbeat or broker execution')`));
await waitFor(`monitorRequests.some(r=>r.path.endsWith('/recovery')&&r.query.includes('policy_id=fixture'))`);
await waitFor(`document.body.innerText.includes('PROTECTION_UNVERIFIED')`);
await click('Older recovery observations');
await waitFor(`document.body.innerText.includes('Previous page retained')`);
assert(await evaluate(`document.body.innerText.includes('PROTECTION_UNVERIFIED')`));
await click('Older recovery observations');
await waitFor(`document.body.innerText.includes('OLDER_UNRESOLVED')`);
await click('Latest recovery observations');
await waitFor(`document.body.innerText.includes('PROTECTION_UNVERIFIED')`);
assert(await evaluate(`document.body.innerText.includes('MT5 automated execution disabled')`));
for(const width of [390,1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
 assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Overflow '+width);
}
await evaluate('window.failMonitor=true');await click('Refresh monitoring');
await waitFor(`document.body.innerText.includes('Displayed data may be stale')`);
assert(await evaluate(`document.body.innerText.includes('NOT_DEPLOYED')`));
await evaluate('window.failMonitor=false');await click('Refresh monitoring');
await waitFor(`!document.body.innerText.includes('Displayed data may be stale')`);
assert(await evaluate(`monitorRequests.every(r=>r.method==='GET')`));
await send('Page.reload');await waitFor(`document.body.innerText.includes('NOT_DEPLOYED')`);
assert.deepEqual(errors,[]);
console.log('Algo monitoring fixture smoke passed: 390/1024/1440/1920; stale/retry; reload; GET-only; no runtime errors.');
await send('Browser.close');close();
