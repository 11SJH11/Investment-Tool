// Opt-in browser fixture: no terminal, original backend or credentials accessed.
import assert from 'node:assert/strict';
const base=process.env.LEDGER_SMOKE_URL;
assert(base&&new URL(base).hostname==='127.0.0.1');
const {send,evaluate,waitFor,errors,close}=await import('./cdp.mjs');
function fixtures(){
 localStorage.clear();localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Settings'));
 window.catalogCalls=[];
 window.fetch=async(url,options={})=>{
  const p=new URL(String(url),location.href).pathname;window.catalogCalls.push(p);let body={items:[]};
  if(p.endsWith('/brokers'))body={items:[{provider:'mt5',profile_id:'mt5-default',environment:'demo',configured:true,supported:true,destination:'journal',account_key:'a'.repeat(64),status:'never_synced'}]};
  else if(p.endsWith('/symbols')||p.endsWith('/symbols/refresh'))body={items:[{name:'NASUSD',description:'Broker Nasdaq CFD',instrument_id:'b'.repeat(64),instrument_type:'cfd',trade_tick_size:.1,canonical_symbol:null,futures_verified:false}],total:1,catalog_total:1,offset:0,observed_at:'2026-10-18T10:00:00Z'};
  else if(p.endsWith('/jobs'))body={jobs:[],compute:{mode:'1',configured_budget:1,used_workers:0}};
  else if(p.endsWith('/data/status'))body={providers:{},symbols_cached:0};
  return new Response(JSON.stringify(body),{headers:{'Content-Type':'application/json'}});
 };
}
await send('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixtures.toString()})()`});
await send('Page.navigate',{url:base+'/?mt5-catalog='+Date.now()});
await waitFor(`document.querySelector('[aria-label="MetaTrader 5 connection"]')`);
assert(await evaluate(`!window.catalogCalls.some(p=>p.includes('/symbols'))`));
await evaluate(`(()=>{[...document.querySelectorAll('summary')].find(e=>e.textContent==='MT5 broker instruments').click();[...document.querySelectorAll('button')].find(e=>e.textContent==='Refresh from terminal').click();})()`);
await waitFor(`document.body.innerText.includes('NASUSD')`);
assert(await evaluate(`window.catalogCalls.some(p=>p.endsWith('/symbols/refresh'))`));
await evaluate(`(()=>{[...document.querySelectorAll('button')].find(e=>e.textContent==='Metadata').click();})()`);
await waitFor(`document.querySelector('[aria-label="Broker symbol metadata"]')`);
assert(await evaluate(`document.querySelector('[aria-label="Broker symbol metadata"]').innerText.includes('Unknown')`));
for(const width of [1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
 assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Overflow at '+width);
}
assert.equal(errors.length,0,errors.join('\n'));
console.log('PASS MT5 catalog explicit refresh, metadata, unknown mapping, 1024/1440/1920, no runtime errors');
close();
