// Mocked UI acceptance only. No broker/provider or production database access.
import assert from 'node:assert/strict';
const base=process.env.LEDGER_SMOKE_URL;
assert(base&&new URL(base).hostname==='127.0.0.1');
const {send,evaluate,waitFor,click,errors,close}=await import('./cdp.mjs');
function fixtures(){
 localStorage.clear();localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Algo Trading'));
 window.requests=[];
 window.fetch=async(url,options={})=>{
  const path=new URL(String(url),location.href).pathname;
  window.requests.push({path,url:String(url),method:options.method||'GET'});
  let data={items:[]};
  if(path.endsWith('/algo-trading'))data={items:[],accounts:[],warnings:[]};
  else if(path.endsWith('/brokers'))data={items:[{profile_id:'demo-fixture',provider:'mt5',environment:'demo',configured:true,account_key:'a'.repeat(64)},{profile_id:'live-fixture',provider:'mt5',environment:'live',configured:true,account_key:'b'.repeat(64)}]};
  else if(path.endsWith('/deployments/preview'))data={estimated_target_risk:50,estimate_currency:'USD',estimate_observed_at:'2026-10-25T12:00:00Z',definition:{strategy_key:'gold_ifvg_v2_fvg_ratio_020',implementation:{source_sha256:'c'.repeat(64)}},warning:'Draft only',blockers:['activation_not_authorized']};
  else if(path.endsWith('/deployments'))data={id:'fixture-draft',state:'DRAFT',execution_enabled:false};
  else if(path.endsWith('/jobs'))data={jobs:[],compute:{mode:'1',configured_budget:1,used_workers:0}};
  return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
 };
}
await send('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixtures.toString()})()`});
await send('Page.navigate',{url:base+'/?deployment-draft'});
await waitFor(`document.body.innerText.includes('Deploy to DEMO')`);
await click('Deploy to DEMO');
await waitFor(`document.querySelector('option[value="demo-fixture"]')`);
assert(!await evaluate(`!!document.querySelector('option[value="live-fixture"]')`));
async function field(label,value){
 await evaluate(`(()=>{const l=[...document.querySelectorAll('label')].find(l=>l.textContent.startsWith(${JSON.stringify(label)}));const el=l.querySelector('input,select');Object.getOwnPropertyDescriptor(el.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set.call(el,${JSON.stringify(value)});el.dispatchEvent(new Event(el.tagName==='SELECT'?'change':'input',{bubbles:true}));})()`);
}
await field('Saved run ID','212');await field('Verified DEMO profile','demo-fixture');await field('Exact discovered','XAUUSDs');await field('Maximum account gross','10000');
await field('Deployment operator token','fixture-private-token-not-real-123456789');
await click('Validate draft');await waitFor(`document.body.innerText.includes('activation_not_authorized')`);
await click('Save unarmed draft');await waitFor(`document.body.innerText.includes('No worker started; no orders authorized.')`);
for(const width of [390,1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
 assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Overflow '+width);
}
assert(await evaluate(`![...Object.values(localStorage),...Object.values(sessionStorage)].some(v=>v.includes('fixture-private-token'))`));
await click('Close deployment configuration');await click('Deploy to DEMO');
assert.equal(await evaluate(`document.querySelector('input[type="password"]').value`),'');
assert(await evaluate(`requests.filter(r=>r.method==='POST').every(r=>r.path.endsWith('/deployments')||r.path.endsWith('/deployments/preview'))`));
assert(await evaluate(`requests.filter(r=>r.path.startsWith('/api/')).every(r=>r.url.startsWith('/api/'))`),'Default API must use the Ledger origin, not the viewing device localhost');
assert.deepEqual(errors,[]);
console.log('PASS unarmed deployment preview/save, DEMO-only list, token memory clearing, no activation calls, 390/1024/1440/1920 layout.');
await send('Browser.close');close();
