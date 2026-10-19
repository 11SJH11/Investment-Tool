// Opt-in, fully mocked saved-run download/provenance acceptance.
import assert from 'node:assert/strict';
const base=process.env.LEDGER_SMOKE_URL;
assert(base&&new URL(base).hostname==='127.0.0.1');
const {send,evaluate,waitFor,click,errors,close}=await import('./cdp.mjs');
await send('Browser.setDownloadBehavior',{behavior:'deny'});
function fixtures(){
 localStorage.clear();localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Backtest'));
 localStorage.setItem('ledger.ui.backtest.tab',JSON.stringify('Runs'));
 window.exportRequests=[];window.downloadBlobs=[];window.selectionBodies=[];window.sectionRequests=[];window.confirm=()=>true;
 const create=URL.createObjectURL.bind(URL);URL.createObjectURL=blob=>{window.downloadBlobs.push(blob);return create(blob);};
 const strategy={key:'fixture',name:'Fixture',timeframes:['1m'],defaults:{},parameters:[]};
 const result={strategy,symbols:['QQQ'],metrics:{trades:0,starting_balance:10000,ending_balance:10000},trades:[],equity_curve:[],analysis:{},experiment_contract:{executor:{kind:'ledger_python',version:'fixture',execution_tier:'fast_bars',source_sha256:'a'.repeat(64)},configuration_sha256:'b'.repeat(64),availability:{microstructure:'UNAVAILABLE'}}};
 const config={strategy_key:'fixture',symbols:['QQQ']};
 window.fetch=async(url,options={})=>{
  const path=new URL(String(url),location.href).pathname;let data={items:[]};
  if(path.endsWith('/export')){window.exportRequests.push(String(url));return new Response('PK-fixture',{headers:{'Content-Type':'application/zip'}});}
  if(path.endsWith('/export-selected')){window.selectionBodies.push(JSON.parse(options.body));return new Response('PK-selected',{headers:{'Content-Type':'application/zip'}});}
  if(path.endsWith('/delete-selected'))return new Response(JSON.stringify({detail:'This run is retained as research evidence'}),{status:409,headers:{'Content-Type':'application/json'}});
  if(path.endsWith('/strategies'))data={strategies:[strategy]};
  else if(path.endsWith('/runs'))data={runs:[1,2].map(id=>({id,name:'Fixture '+id,strategy_key:'fixture',strategy_name:'Fixture',symbols:['QQQ'],trades:0,tags:[],test_role:'development',created_at:'2026-01-01'}))};
  else if(path.includes('/sections/')){window.sectionRequests.push(path);data={id:Number(path.match(/runs\/(\d+)/)[1]),name:'Fixture',config,result};}
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
await click('Back to Runs');
await waitFor(`document.querySelector('[aria-label="Select Saved runs row 1"]')`);
await evaluate(`document.querySelector('[aria-label="Select Saved runs row 1"]').click()`);
await waitFor(`document.querySelector('[aria-label="Selected run actions"]')`);
assert(await evaluate(`document.querySelector('[aria-label="Selected run actions"]').innerText.includes('Use settings')`));
await evaluate(`document.querySelector('[aria-label="Select Saved runs row 2"]').click()`);
await waitFor(`document.body.innerText.includes('Compare selected')`);
assert(await evaluate(`!window.sectionRequests.some(p=>p.includes('/runs/2/'))`));
await click('Compare selected');
await waitFor(`window.sectionRequests.some(p=>p.includes('/runs/2/'))`);
await click('Download selected / analysis bundle');
await waitFor(`window.downloadBlobs.length===2`);
assert.deepEqual(await evaluate(`window.selectionBodies[0].run_ids`),[1,2]);
await click('Delete selected');
await waitFor(`document.body.innerText.includes('retained as research evidence')`);
assert(await evaluate(`document.querySelector('[aria-label="Selected run actions"]').innerText.includes('2 selected')`));
for(const width of [1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
 assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Overflow '+width);
}
assert.equal(errors.length,0,errors.join('\n'));
await click('Clear selection');
await waitFor(`!document.querySelector('[aria-label="Selected run actions"]')`);
console.log('PASS provenance, binary single/bulk downloads, selection actions, protected deletion and clear; 1024/1440/1920, no runtime errors');
close();
