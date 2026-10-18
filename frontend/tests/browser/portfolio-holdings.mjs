// Mock API smoke: current holdings and stale-snapshot disclosure.
import assert from 'node:assert/strict';
const base=process.env.LEDGER_SMOKE_URL;
assert(base&&new URL(base).hostname==='127.0.0.1');
const {send,evaluate,waitFor,errors,close}=await import('./cdp.mjs');
function fixtures(){
 localStorage.clear();localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Investment Portfolio'));
 window.fetch=async(url)=>{
  const path=new URL(String(url),location.href).pathname;let data={items:[]};
  if(path.endsWith('/broker-accounts'))data={items:[{account_key:'fixture',provider:'trading212',label:'Demo',sync_status:'error',synced_at:'2026-10-16T12:00:00Z',summary:{currency:'USD',totalValue:100,cash:{availableToTrade:0},investments:{totalCost:90,unrealizedProfitLoss:10}}}]};
  else if(path.endsWith('/broker-records'))data={total:1,items:[{id:1,active:1,kind:'position',note:'Preserved',tags:[],facts:{instrument:{ticker:'AAPL',name:'Current holding',currency:'USD'},quantity:1,walletImpact:{currentValue:100,currency:'USD'}}}]};
  else if(path.endsWith('/portfolio'))data={holdings:[],transactions:[],accounts:[],summary:{}};
  else if(path.endsWith('/jobs'))data={jobs:[],max_workers:1};
  return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
 };
}
await send('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixtures.toString()})()`});
await send('Page.navigate',{url:base+'/?holdings='+Date.now()});
await waitFor(`document.body.innerText.includes('Current holding')`);
assert(await evaluate(`document.body.innerText.includes('last verified holdings')`));
assert(await evaluate(`!document.body.innerText.includes('previous snapshot')`));
for(const width of [1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
 assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Overflow '+width);
}
assert.equal(errors.length,0,errors.join('\n'));
console.log('PASS current holdings and stale notice; 1024/1440/1920, no runtime errors');
close();
