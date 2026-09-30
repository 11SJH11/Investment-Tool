// Mocked APIs and isolated browser profile only; never touches running research.
import assert from 'node:assert/strict';
const base=process.env.LEDGER_SMOKE_URL;
assert(base&&new URL(base).hostname==='127.0.0.1');
const {send,evaluate,click,waitFor,errors,close}=await import('./cdp.mjs');
function fixtures(){
 localStorage.clear(); localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Settings'));
 // A legacy auto-warm preference must no longer start a hidden download.
 localStorage.setItem('ledger.preferences',JSON.stringify({keepFavouritesUpdated:true,favouriteCacheLookbackDays:730}));
 window.requests=[];window.warmJobs=[];
 window.fetch=async(url,options={})=>{
  const p=new URL(String(url),location.href).pathname,method=options.method||'GET';
  requests.push({p,method,body:options.body?JSON.parse(options.body):null});let body={};
  if(p==='/api/data/cache/warm'){
   if(method==='POST')warmJobs=[{id:'fixture',symbols:['NQ1!'],status:'running',completed:0,total:1,chunks_completed:1,provider_state:'waiting_or_fetching',current_chunk:{symbol:'NQ1!',start:'2026-09-16T00:00Z',end:'2026-09-23T00:00Z'},items:[{symbol:'NQ1!',requested_start:'2024-09-30T00:00Z',requested_end:'2026-09-30T00:00Z',downloaded_coverage:['2026-09-23T00:00Z','2026-09-30T00:00Z']}]}];
   body=method==='POST'?warmJobs[0]:{items:warmJobs};
  }else if(p.endsWith('/fixture/pause')){warmJobs[0].status='paused';warmJobs[0].provider_state='paused';body=warmJobs[0]}
  else if(p.endsWith('/fixture/resume')){warmJobs[0].status='running';warmJobs[0].provider_state='waiting_or_fetching';body=warmJobs[0]}
  else if(p==='/api/data/cache')body={items:[],note:'Coverage is requested history, including closed sessions.'};
  else if(p.endsWith('/compute-settings'))body={mode:'auto_conservative',resolved_workers:2};
  else if(p.endsWith('/brokers'))body={items:[]};
  else if(p.endsWith('/strategies'))body={strategies:[]};
  else if(p.endsWith('/indicators'))body={indicators:[]};
  else if(p.endsWith('/runs'))body={runs:[]};
  else if(p.endsWith('/jobs'))body={jobs:[]};
  else if(p.endsWith('/research-experiments'))body={experiments:[]};
  else if(p.endsWith('/strategy-workspace/files'))body={files:[],template:'',default_filename:'_workspace_fixture.py'};
  return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}});
 };
}
await send('Page.navigate',{url:'about:blank'});
await waitFor(`location.href==='about:blank'`);
errors.length=0;
await send('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixtures.toString()})()`});
await send('Page.navigate',{url:base});
try{
 await waitFor(`document.querySelector('[aria-label="Background history downloads"]')`);
 assert.equal(await evaluate(`requests.filter(r=>r.p==='/api/data/cache/warm'&&r.method==='POST').length`),0);
 await click('Update missing NQ1! data');
 await waitFor(`document.body.innerText.includes('NQ1! | running')`);
 assert(await evaluate(`document.body.innerText.includes('2024-09-30')&&document.body.innerText.includes('Covered requests: 2026-09-23')&&document.body.innerText.includes('Current chunk: NQ1!')`));
 await click('Pause');await waitFor(`document.body.innerText.includes('NQ1! | paused')`);
 await click('Overview');await waitFor(`!document.querySelector('[aria-label="Background history downloads"]')`);
 await click('Settings');await waitFor(`document.body.innerText.includes('NQ1! | paused')`);
 await click('Resume');await waitFor(`document.body.innerText.includes('NQ1! | running')`);
 await evaluate(`warmJobs[0].status='failed';warmJobs[0].provider_state='rate_limited';warmJobs[0].error='Provider rate limited; resume after the cooldown.';warmJobs[0].retry_at='2099-01-01T00:00:00Z'`);
 await click('Refresh download status');await waitFor(`document.body.innerText.includes('Provider rate limited')`);
 assert(await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='Resume').disabled`));
 for(const width of [1024,1440,1920]){
  await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
  assert(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),`overflow at ${width}`);
 }
 assert.equal(await evaluate(`requests.filter(r=>r.p==='/api/data/cache/warm'&&r.method==='POST').length`),1);
 assert.equal(errors.length,0,errors.join('\n'));
 console.log('PASS explicit download, legacy auto-warm disabled, requested/covered/chunk status, pause/resume, navigation persistence, cooldown, 1024/1440/1920 and runtime checks');
}finally{if(errors.length)console.error(errors);close()}
