// Opt-in, isolated Run Viewer source export check. Every API response is mocked.
import assert from 'node:assert/strict';
const base=process.env.LEDGER_SMOKE_URL;
assert(base&&new URL(base).hostname==='127.0.0.1');
const {send,evaluate,waitFor,click,errors,close}=await import('./cdp.mjs');
function fixtures(){
 localStorage.clear();localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Backtest'));localStorage.setItem('ledger.ui.backtest.tab',JSON.stringify('Runs'));
 window.requests=[];window.downloads=[];window.downloadBlobs=[];
 URL.createObjectURL=blob=>{window.downloadBlobs.push(blob);return 'blob:fixture';};URL.revokeObjectURL=()=>{};
 HTMLAnchorElement.prototype.click=function(){window.downloads.push(this.download);};
 const strategy={key:'fixture',name:'Source fixture',defaults:{},parameters:[],timeframes:['1m']};
 window.fetch=async(url)=>{const p=new URL(String(url),location.href).pathname;requests.push(p);let body={items:[]};
 if(p.endsWith('/strategies'))body={strategies:[strategy]};
 else if(p.endsWith('/indicators'))body={indicators:[]};
 else if(p.endsWith('/jobs'))body={jobs:[],compute:{used_workers:0}};
 else if(p.endsWith('/runs'))body={runs:[1,2].map(id=>({id,name:id===1?'Archived source':'Legacy source',strategy_key:'fixture',strategy_name:'Source fixture',symbols:['QQQ'],created_at:'2026-10-09T12:00:00Z',test_role:'development',trades:0,tags:[]}))};
 else if(p.endsWith('/reproducibility'))body={format:'ledger_reproducibility_manifest_v1',execution_environment:null,replayable_archive:false,missing_artifacts:['Historical bar archive']};
 else if(p.endsWith('/source-archive'))body={format:'ledger_strategy_source_bundle_v1',encoding:'base64',files:{'fixture.py':'IyBmaXh0dXJl'},manifest:{'fixture.py':'fixture-hash'}};
 else if(p.includes('/sections/')){const id=Number(p.split('/runs/')[1].split('/')[0]);body={id,name:id===1?'Archived source':'Legacy source',section:'summary',config:{strategy_key:'fixture',symbols:['QQQ']},result:{strategy:{...strategy,implementation:{source_sha256:'fixture-hash'},...(id===1?{source_archive:{status:'archived',sha256:'registry-hash'}}:{})},symbols:['QQQ'],primary_timeframe:'1m',metrics:{trades:0,starting_balance:10000,ending_balance:10000},equity_curve:[],execution_model:{}}};}
 return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}});
 };
}
await send('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixtures.toString()})()`});
await send('Page.navigate',{url:base+'/?source-archive-smoke='+Date.now()});
await waitFor(`document.body.innerText.includes('Archived source')`);
await evaluate(`[...document.querySelectorAll('tr')].find(r=>r.textContent.includes('Archived source')).querySelector('button').click()`);
await waitFor(`document.body.innerText.includes('Loaded strategy source archived')`);
assert(await evaluate(`!requests.some(p=>p.endsWith('/source-archive'))`));
await click('Export recorded strategy source');
await waitFor(`downloads.length===1`);
const bundle=await evaluate(`downloadBlobs[0].text().then(JSON.parse)`);
assert.equal(bundle.format,'ledger_strategy_source_bundle_v1');assert.equal(bundle.files['fixture.py'],'IyBmaXh0dXJl');
for(const width of [1024,1440,1920]){await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Viewer overflow '+width);}
assert(await evaluate(`!requests.some(p=>p.endsWith('/reproducibility'))`));
await click('Export reproducibility manifest');await waitFor(`downloads.length===2`);
const manifest=await evaluate(`downloadBlobs[1].text().then(JSON.parse)`);
assert.equal(manifest.format,'ledger_reproducibility_manifest_v1');assert.equal(manifest.execution_environment,null);assert.equal(manifest.replayable_archive,false);
await click('Runs');await waitFor(`document.body.innerText.includes('Legacy source')`);
await evaluate(`[...document.querySelectorAll('tr')].find(r=>r.textContent.includes('Legacy source')).querySelector('button').click()`);
await waitFor(`document.body.innerText.includes('No recorded strategy source bundle')`);
assert(await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='Export recorded strategy source').disabled`));
assert(await evaluate(`requests.filter(p=>p.endsWith('/source-archive')).length===1`));
assert.equal(errors.length,0,errors.join('\n'));
console.log('PASS explicit source-bundle export, no eager source fetch, legacy unavailable state, 1024/1440/1920 overflow and runtime checks.');
close();
