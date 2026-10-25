// Explicitly mocked account observations; no real broker calls.
import assert from 'node:assert/strict';
const base=process.env.LEDGER_SMOKE_URL;
assert(base&&new URL(base).hostname==='127.0.0.1');
const {send,evaluate,waitFor,click,errors,close}=await import('./cdp.mjs');
function fixtures(){
 localStorage.clear();localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Algo Trading'));
 window.requests=[];window.failAccount=false;
 const facts={currency:'USD',balance:10000,equity:9990,margin:100,margin_free:9890};
 const snapshot={account:facts,environment:'demo',observed_at:'2026-10-25T10:00:00Z',warning:'Fixture sequential read only.',positions:Array.from({length:150},(_,i)=>({ticket:i,symbol:'FIXTURE-GOLD',type:1,volume:.1,price_open:4000,price_current:4001,sl:4010,tp:3980,profit:-10,swap:-1})),pending_orders:[]};
 snapshot.account_key='a'.repeat(64);
 const detail={snapshot,history:[{id:1,observed_at:'2026-10-25T09:00:00Z',currency:'USD',equity:10000},{id:2,observed_at:snapshot.observed_at,currency:'USD',equity:9990}]};
 const report={observed_at:'2026-10-25T12:00:00Z',items:[],warnings:[],accounts:[{profile_id:'demo-fixture',provider:'mt5',environment:'demo',configured:true,account_key:'a'.repeat(64),observation:{facts,observed_at:snapshot.observed_at,position_count:150,pending_order_count:0}}],broker_totals:[{environment:'demo',currency:'USD',accounts:1,balance:10000,equity:9990,oldest_observed_at:snapshot.observed_at,newest_observed_at:snapshot.observed_at}]};
 window.fetch=async(url,options={})=>{
  const path=new URL(String(url),location.href).pathname;window.requests.push({path,method:options.method||'GET'});
  let data={items:[]};
  if(path.endsWith('/account-snapshot')){
   if(window.failAccount)return new Response(JSON.stringify({detail:'Fixture broker disconnected'}),{status:503,headers:{'Content-Type':'application/json'}});
   data=snapshot;
  }else if(path.endsWith('/account-observations'))data=detail;
  else if(path.endsWith('/algo-trading'))data=report;
  else if(path.endsWith('/jobs'))data={jobs:[],compute:{mode:'1',configured_budget:1,used_workers:0}};
  return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
 };
}
await send('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixtures.toString()})()`});
await send('Page.navigate',{url:base+'/?account-observations'});
await waitFor(`document.body.innerText.includes('Observed balance 10000.00 USD')`);
assert(await evaluate(`requests.every(r=>r.method==='GET')`));
await click('View recorded details');
await waitFor(`document.querySelector('[aria-label="Observed account equity chart"] canvas')`);
assert(await evaluate(`document.body.innerText.includes('none are attributed to T01')`));
assert(await evaluate(`document.querySelectorAll('tbody tr').length<=20`),'Position table must paginate');
assert(await evaluate(`requests.every(r=>r.method==='GET')`));
await click('Refresh broker observation');
await waitFor(`requests.some(r=>r.path.endsWith('/account-snapshot')&&r.method==='POST')`);
await waitFor(`[...document.querySelectorAll('button')].some(b=>b.textContent==='Refresh broker observation'&&!b.disabled)`);
await evaluate('window.failAccount=true');await click('Refresh broker observation');
await waitFor(`document.body.innerText.includes('Previous facts are retained')`);
assert(await evaluate(`document.body.innerText.includes('Observed equity 9990.00 USD')`));
for(const width of [390,1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
 assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Overflow '+width);
}
assert(await evaluate(`requests.filter(r=>r.method!=='GET').every(r=>r.path.endsWith('/account-snapshot'))`));
assert.deepEqual(errors,[]);
console.log('PASS observed equity, lazy stored details, explicit read-only refresh, failure retention, pagination and 390/1024/1440/1920 layouts.');
await send('Browser.close');close();
