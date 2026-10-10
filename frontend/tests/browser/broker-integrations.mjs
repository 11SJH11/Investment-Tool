// Opt-in browser smoke; all backend/provider traffic is mocked before app load.
import assert from 'node:assert/strict';
const base=process.env.LEDGER_SMOKE_URL;
assert(base&&new URL(base).hostname==='127.0.0.1');
const {send,evaluate,waitFor,click,errors,close}=await import('./cdp.mjs');
function fixtures(){
 localStorage.clear();localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Settings'));
 window.integrationCalls=[];
 const accounts=[{provider:'trading212',account_key:'a',label:'Trading 212 account',synced_at:'2026-10-07T10:00:00Z',summary:{currency:'USD',totalValue:120}},{provider:'robinhood',account_key:'b',label:'Robinhood account',synced_at:'2026-10-07T10:00:00Z',summary:{currency:'USD',totalValue:230}}];
 window.fetch=async(url,options={})=>{
  const u=new URL(String(url),location.href),p=u.pathname;integrationCalls.push({path:p,method:options.method||'GET'});let body={items:[]};
  if(p.endsWith('/brokers'))body={items:[{provider:'robinhood',profile_id:'robinhood-default',environment:'live',configured:true,supported:true,execution:false,destination:'portfolio',status:'never_synced',discovered_capabilities:{equities_read:true,ledger_execution:false}}]};
  else if(p.endsWith('/test'))body={status:'connected',items:[{account_key:'b',label:'Robinhood account',currency:'USD'}]};
  else if(p.endsWith('/sync'))body={status:'success',created:1,updated:0};
  else if(p.endsWith('/futures/diagnostics'))body={providers:{mt5:{status:'connected',bars:10,first_bar:'2026-09-01',latest_bar:'2026-09-02',first_request_seconds:1,cached_request_seconds:.01,gap_intervals:0}},note:'Fixture comparison only; routing unchanged.'};
  else if(p.endsWith('/broker-accounts'))body={items:accounts};
  else if(p.endsWith('/broker-records'))body={total:1,items:[{id:u.searchParams.get('account_key')==='a'?1:2,active:1,provider:u.searchParams.get('account_key')==='a'?'trading212':'robinhood',kind:'position',external_id:'fixture',facts:{instrument:{ticker:'AAPL',currency:'USD'},quantity:2,walletImpact:{currency:'USD',currentValue:200}},note:'Keep',tags:[]}]};
  else if(p.endsWith('/portfolio'))body={holdings:[],transactions:[],accounts:[],base_currency:'USD'};
  else if(p.endsWith('/jobs'))body={jobs:[],compute:{mode:'1',configured_budget:1,used_workers:0}};
  else if(p.endsWith('/data/status'))body={providers:{},symbols_cached:0};
  return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}});
 };
}
await send('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixtures.toString()})()`});
await send('Page.navigate',{url:base+'/?integration-smoke='+Date.now()});
await waitFor(`document.querySelector('[aria-label="Robinhood connection"]')`);
assert(await evaluate(`!integrationCalls.some(c=>c.method==='POST')`));
assert(await evaluate(`document.querySelector('[aria-label="Robinhood environment"]').options.length===1`));
await click('Test connection');await waitFor(`document.querySelector('[aria-label="Robinhood account"]')`);
await click('Sync now');await waitFor(`document.body.innerText.includes('Imported 1')`);
await evaluate(`(()=>{const inputs=[...document.querySelectorAll('input[type=date]')];for(let i=0;i<inputs.length;i++){Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(inputs[i],i?'2026-09-02':'2026-09-01');inputs[i].dispatchEvent(new Event('input',{bubbles:true}));}})()`);
await click('Test MT5 history');await waitFor(`document.body.innerText.includes('MT5: connected')`);
for(const width of [1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
 assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Settings overflow '+width);
}
await click('Portfolio');await waitFor(`document.body.innerText.includes('Broker account totals')`);
assert(await evaluate(`document.body.innerText.includes('350.00')`));
await evaluate(`(()=>{const label=[...document.querySelectorAll('label')].find(l=>l.textContent.startsWith('Broker '));const el=label.querySelector('select');el.value='robinhood';el.dispatchEvent(new Event('change',{bubbles:true}));})()`);
await waitFor(`document.body.innerText.includes('230.00')&&!document.body.innerText.includes('350.00')`);
for(const width of [1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
 assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Portfolio overflow '+width);
}
assert.equal(errors.length,0,errors.join('\n'));
console.log('PASS Robinhood cards/live-only/test/sync, no automatic POST, MT5 diagnostics, Portfolio broker filtering and totals; 1024/1440/1920; no runtime errors.');
close();
