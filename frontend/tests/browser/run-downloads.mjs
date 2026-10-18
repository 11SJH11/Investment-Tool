// Opt-in, fully mocked saved-run download/provenance acceptance.
import assert from 'node:assert/strict';
const base=process.env.LEDGER_SMOKE_URL;
assert(base&&new URL(base).hostname==='127.0.0.1');
const {send,evaluate,waitFor,click,errors,close}=await import('./cdp.mjs');
await send('Browser.setDownloadBehavior',{behavior:'deny'});
function fixtures(){
 localStorage.clear();localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Backtest'));
 localStorage.setItem('ledger.ui.backtest.tab',JSON.stringify('Runs'));
 window.exportRequests=[];window.downloadBlobs=[];
 const create=URL.createObjectURL.bind(URL);URL.createObjectURL=blob=>{window.downloadBlobs.push(blob);return create(blob);};
 const strategy={key:'fixture',name:'Fixture',timeframes:['1m'],defaults:{},parameters:[]};
 const result={strategy,symbols:['QQQ'],metrics:{trades:0,starting_balance:10000,ending_balance:10000},trades:[],equity_curve:[],analysis:{},experiment_contract:{executor:{kind:'ledger_python',version:'fixture',execution_tier:'fast_bars',source_sha256:'a'.repeat(64)},configuration_sha256:'b'.repeat(64),availability:{microstructure:'UNAVAILABLE'}}};
 const config={strategy_key:'fixture',symbols:['QQQ']};
 window.fetch=async(url)=>{
  const path=new URL(String(url),location.href).pathname;let data={items:[]};
  if(path.endsWith('/export')){window.exportRequests.push(String(url));return new Response('PK-fixture',{headers:{'Content-Type':'application/zip'}});}
  if(path.endsWith('/strategies'))data={strategies:[strategy]};
  else if(path.endsWith('/runs'))data={runs:[{id:1,name:'Fixture',strategy_key:'fixture',strategy_name:'Fixture',symbols:['QQQ'],trades:0,tags:[],test_role:'development',created_at:'2026-01-01'}]};
  else if(path.includes('/sections/'))data={id:1,name:'Fixture',config,result};
  else if(path.endsWith('/jobs'))data={jobs:[],max_workers:1};
  else if(path.endsWith('/indicators'))data={indicators:[]};
  else if(path.endsWith('/research-experiments'))data={experiments:[]};
  return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
 };
}
await send('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixtures.toString()})()`});
await send('Page.navigate',{url:base+'/?downloads='+Date.now()});
await waitFor(`[...document.querySelectorAll('button')].some(b=>b.textContent==='Open')`);
await click('Open');
await waitFor(`document.querySelector('[aria-label="Download saved research evidence"]')`);
await evaluate(`(()=>{[...document.querySelectorAll('summary')].find(e=>e.textContent==='Recorded experiment provenance').click()})()`);
assert(await evaluate(`document.body.innerText.includes('ledger python')`));
await evaluate(`document.querySelector('[aria-label="Download saved research evidence"] button').click()`);
await waitFor(`window.downloadBlobs.length===1`);
assert.equal(await evaluate(`window.downloadBlobs[0].type`),'application/zip');
assert(await evaluate(`window.exportRequests[0].endsWith('kind=bundle')`));
for(const width of [1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
 assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Overflow '+width);
}
assert.equal(errors.length,0,errors.join('\n'));
console.log('PASS recorded executor provenance and binary bundle download; 1024/1440/1920, no runtime errors');
close();
