// Opt-in production smoke. All observations below are explicitly mocked.
import assert from 'node:assert/strict';
const base=process.env.LEDGER_SMOKE_URL;
assert(base&&new URL(base).hostname==='127.0.0.1');
const {send,evaluate,waitFor,click,errors,close}=await import('./cdp.mjs');
function fixtures(){
 localStorage.clear();localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Algo Trading'));
 window.monitorRequests=[];window.failMonitor=false;
 const report={observed_at:'2026-10-22T12:00:00Z',accounts:[],warnings:[],limitation:'Fixture observations only',items:[{id:'fixture',name:'T01 preparation fixture',mode:'MT5_PREPARATION',environment:'demo',symbol:'XAUUSD',status:'NOT_DEPLOYED',persisted_status:'DISABLED',source_hash:'fixture-hash',metrics:null,trades:[],risk:{},limitation:'Saved policy only'}]};
 report.recovery_observations=[{id:'recovery',policy_id:'fixture',intent_id:'intent',observed_at_ms:1000000,state:'PROTECTION_UNVERIFIED',identity_basis:'durable_attempt_receipt',complete:true,filled_lots:'0.1',remaining_lots:'0.1'}];
 window.fetch=async(url,options={})=>{
  const path=new URL(String(url),location.href).pathname;window.monitorRequests.push({path,method:options.method||'GET'});
  if(path.endsWith('/algo-trading')&&window.failMonitor)return new Response(JSON.stringify({detail:'Fixture outage'}),{status:503,headers:{'Content-Type':'application/json'}});
  const data=path.endsWith('/algo-trading')?report:path.endsWith('/jobs')?{jobs:[],compute:{mode:'1',configured_budget:1,used_workers:0}}:{items:[]};
  return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
 };
}
await send('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixtures.toString()})()`});
await send('Page.navigate',{url:base+'/?algo-monitoring-smoke'});
await waitFor(`document.body.innerText.includes('NOT_DEPLOYED')`);
assert(await evaluate(`document.body.innerText.includes('PROTECTION_UNVERIFIED')&&document.body.innerText.includes('Protection evidence may be stale')`));
await click('Inspect');
await waitFor(`document.querySelector('[aria-label="Strategy monitoring detail"]')`);
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
