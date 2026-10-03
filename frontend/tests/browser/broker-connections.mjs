// Opt-in isolated browser acceptance. Every API response is mocked.
import assert from 'node:assert/strict';
const base=process.env.LEDGER_SMOKE_URL;
assert(base&&new URL(base).hostname==='127.0.0.1');
const {send,evaluate,waitFor,errors,close}=await import('./cdp.mjs');
function fixtures(){
 localStorage.clear();localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Settings'));
 window.brokerCalls=[];
 window.profiles=['trading212','tradelocker','mt5'].map(provider=>({provider,profile_id:provider+'-default',environment:'demo',configured:true,supported:true,read_only:true,execution:false,destination:provider==='trading212'?'portfolio':'journal',status:'never_synced',auto_sync:{enabled:true,interval_seconds:provider==='trading212'?300:60,minimum_seconds:provider==='trading212'?300:60,status:'scheduled'}}));
 window.fetch=async(url,options={})=>{
  const p=new URL(String(url),location.href).pathname;let body={items:[]};window.brokerCalls.push({path:p,method:options.method||'GET',body:options.body});
  const profile=window.profiles.find(x=>p.includes('/'+x.profile_id+'/'));
  if(p.endsWith('/brokers'))body={items:window.profiles};
  else if(profile&&p.endsWith('/test'))body={status:'connected',items:[{account_key:'a'.repeat(64),label:'Verified demo account',currency:'USD'}]};
  else if(profile&&p.endsWith('/account')){profile.account_key=JSON.parse(options.body).account_key;profile.account='Verified demo account';body=profile;}
  else if(profile&&p.endsWith('/connection')){const config=JSON.parse(options.body);Object.assign(profile,{configured:config.enabled,environment:config.environment,disconnected:!config.enabled,status:config.enabled?'never_synced':'disconnected'});body=profile;}
  else if(profile&&p.endsWith('/sync')){profile.status='success';profile.last_success_at='2026-10-03T12:00:00Z';body={status:'success',created:1,updated:0};}
  else if(p.endsWith('/jobs'))body={jobs:[],compute:{mode:'1',configured_budget:1,used_workers:0}};
  else if(p.endsWith('/data/status'))body={providers:{},symbols_cached:0};
  return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}});
 };
}
await send('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixtures.toString()})()`});
await send('Page.navigate',{url:base+'/?broker-test='+Date.now()});
await waitFor(`document.querySelector('[aria-label="TradeLocker connection"]')`);
const button=(provider,text)=>evaluate(`(()=>{const card=document.querySelector('[aria-label="${provider} connection"]');const b=[...card.querySelectorAll('button')].find(x=>x.textContent===${JSON.stringify(text)});if(!b||b.disabled)throw Error('Unavailable action');b.click();})()`);
assert(await evaluate(`document.body.innerText.includes('MT4 is not supported')`));
assert(await evaluate(`!window.brokerCalls.some(x=>x.path.endsWith('/test')||x.path.endsWith('/sync'))`));
await button('TradeLocker','Test connection');
await waitFor(`document.querySelector('[aria-label="TradeLocker account"]')`);
await evaluate(`(()=>{const el=document.querySelector('[aria-label="TradeLocker account"]');el.value='a'.repeat(64);el.dispatchEvent(new Event('change',{bubbles:true}));})()`);
await waitFor(`document.body.innerText.includes('Verified account selected.')`);
await button('TradeLocker','Sync now');await waitFor(`document.body.innerText.includes('Imported 1')`);
await button('TradeLocker','Disconnect');await waitFor(`document.body.innerText.includes('Disconnected locally.')`);
assert(await evaluate(`(()=>{const c=document.querySelector('[aria-label="TradeLocker connection"]');return [...c.querySelectorAll('button')].find(b=>b.textContent==='Sync now').disabled;})()`));
await button('TradeLocker','Enable connection');await waitFor(`document.body.innerText.includes('Connection preferences saved.')`);
await evaluate(`(()=>{const el=document.querySelector('[aria-label="TradeLocker environment"]');el.value='live';el.dispatchEvent(new Event('change',{bubbles:true}));})()`);
await waitFor(`document.querySelector('[aria-label="TradeLocker connection"]').innerText.includes('TradeLocker / live')`);
assert(await evaluate(`!document.querySelector('input[type=password]')`));
for(const width of [1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
 assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Page overflow at '+width);
}
assert.equal(errors.length,0,errors.join('\n'));
console.log('PASS broker cards, zero automatic import on page load, test/discovery/account selection/sync/disconnect/environment, MT5 instructions, no secret inputs, 1024/1440/1920, no runtime errors');
close();
