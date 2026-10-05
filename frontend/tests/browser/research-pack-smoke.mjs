import fs from 'node:fs';
import {send,evaluate,waitFor,click,errors,close,screenshot} from './cdp.mjs';
errors.length=0; // Ignore buffered exceptions from earlier documents; capture this navigation.
await send('Page.addScriptToEvaluateOnNewDocument',{source:`
localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Backtest'));localStorage.setItem('ledger.ui.backtest.tab',JSON.stringify('Backtest'));
window.requests=[];window.originalFetch=window.fetch.bind(window);window.jobState='running';
const strategy={key:'smoke',name:'Review smoke',description:'Fixture',timeframes:['1m'],defaults:{length:2},parameters:[{key:'length',label:'Length',kind:'int',default:2,minimum:1,step:1}]};
const trade={symbol:'SPY',direction:'long',entry_time:'2026-09-28T13:34:00Z',exit_time:'2026-09-28T13:36:00Z',entry_price:106,exit_price:99,stop_loss:90,take_profit:120,net_pnl:-7,r_multiple:-.4,result:'loss',exit_reason:'strategy_exit',metadata:{}};
const result={strategy,metrics:{trades:1,starting_balance:10000,ending_balance:9993},symbols:['SPY'],primary_timeframe:'1m',session:'regular',equity_curve:[],execution_model:{}};
const trades=Array.from({length:103},(_,i)=>({...trade,entry_time:new Date(Date.parse(trade.entry_time)+i*86400000).toISOString(),exit_time:new Date(Date.parse(trade.exit_time)+i*86400000).toISOString()}));
result.equity_curve=trades.map((t,i)=>({timestamp:t.exit_time,equity:10000-i*7,drawdown_pct:-i*.07,return_pct:-i*.07}));
const config={strategy_key:'smoke',strategy_params:{length:2}};
window.fetch=async(url,opts={})=>{if(String(url).startsWith('blob:'))return window.originalFetch(url,opts);const path=new URL(String(url),location.origin).pathname;window.requests.push(path);let data={items:[]};
if(path.endsWith('/strategies'))data={strategies:[strategy]};
else if(path.endsWith('/indicators'))data={indicators:[]};
else if(path.endsWith('/jobs'))data={jobs:[{id:'one',batch_id:'batch',status:window.jobState,processed:1,total:2,run_id:1,payload:{run_name:'Smoke run',strategy_key:'smoke',symbols:['SPY']}}],max_workers:1,compute:{used_workers:0}};
else if(path.includes('/sections/')){await new Promise(r=>setTimeout(r,250));const section=path.split('/').at(-1);data={id:1,name:'Smoke run',created_at:'2026-09-28T14:00Z',config,section,result:section==='summary'?result:section==='trades'?{trades}:{analysis:{},setups:[],rejected_signals:[]}};}
else if(path.endsWith('/review')){const index=Number(path.split('/').at(-2));if(window.failReview)throw new Error('Fixture history unavailable');const bars=Array.from({length:100},(_,i)=>({timestamp:new Date(Date.parse('2026-09-28T12:40Z')+index*86400000+i*60000).toISOString(),open:(index%2?714:737)+Math.sin(i)*.3+.5,high:(index%2?714:737)+1.5,low:(index%2?714:737),close:(index%2?714:737)+Math.cos(i)*.3+.7,volume:100}));data={bars,symbol:'SPY',config,review:{series:[{id:'vwap',label:'VWAP',timeframe:'1m',overlay:true,role:'strategy_evidence',points:bars.map(b=>({timestamp:b.timestamp,available_at:new Date(Date.parse(b.timestamp)+60000).toISOString(),value:b.close}))},{id:'context',label:'Daily regime EMA',timeframe:'1d',overlay:true,role:'strategy_evidence',points:bars.map(b=>({timestamp:b.timestamp,available_at:new Date(Date.parse(b.timestamp)+60000).toISOString(),value:index%2?713.5:709}))}],levels:[],highlights:[{timestamp:bars[2].timestamp,kind:'entry'}],warnings:['Reconstructed fixture'],evidence:{entry:[{label:'Signal close',value:106,provenance:'recorded'}],exit:[{label:'Exit reason',value:'strategy_exit',provenance:'recorded'}]}}};}
else if(path.endsWith('/runs'))data={runs:[{id:1,name:'Smoke run',strategy_key:'smoke',strategy_name:'Review smoke',symbols:['SPY'],created_at:'2026-09-28T14:00Z',test_role:'development',trades:1,tags:[]}]};
else if(path.includes('preview'))data={job_count:2,axes:[{parameter:'length',labels:['1','2']}]};
else if(path.endsWith('/research-experiments')&&opts.method==='POST')data={job_count:2,experiment_group:'smoke-group'};
else if(path.endsWith('/research-experiments'))data={experiments:[]};
return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}});};
`});
await send('Page.navigate',{url:process.env.LEDGER_SMOKE_URL||'http://127.0.0.1:19283'});
await waitFor(`document.querySelector('[aria-label="Length mode"]')`);
await evaluate(`(()=>{let e=document.querySelector('[aria-label="Length mode"]');e.value='explicit';e.dispatchEvent(new Event('change',{bubbles:true}))})()`);
await waitFor(`document.body.textContent.includes('2 parameter combinations')`);
await click('Run 2 tests');await waitFor(`document.body.textContent.includes('Queued. Follow progress')`);
if(await evaluate(`document.querySelector('[aria-label="Backtest navigation"] [aria-current="page"]').textContent.includes('Viewer')`))throw Error('Auto navigation');
await click('Runs');await waitFor(`[...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='Open')`);await click('Open');
await waitFor(`document.body.textContent.includes('Opening Run #1')`);

await waitFor(`document.querySelector('[aria-label="Run viewer sections"]')`);
await evaluate(`document.querySelectorAll('[aria-label="Run viewer sections"] button')[1].click()`);
await waitFor(`document.body.textContent.includes('View chart')`);await click('View chart');
await waitFor(`document.body.textContent.includes('Trade 1 of 103 filtered trades')`);
await waitFor(`document.querySelector('[data-price-min]')`);
var domain=await evaluate(`({min:Number(document.querySelector('[data-price-min]').dataset.priceMin),max:Number(document.querySelector('[data-price-min]').dataset.priceMax),notes:document.querySelector('[aria-label="Price scale evidence"]').textContent})`);if(domain.min<735||domain.max>741||!domain.notes.includes('709'))throw Error('Distant context dominated scale '+JSON.stringify(domain));
await click('Next trade (K)');await waitFor(`document.body.textContent.includes('Trade 2 of 103 filtered trades')`);
await waitFor(`Number(document.querySelector('[data-price-min]')?.dataset.priceMin)<714`);var nearby=await evaluate(`({min:Number(document.querySelector('[data-price-min]').dataset.priceMin),max:Number(document.querySelector('[data-price-min]').dataset.priceMax)})`);if(nearby.min>=713.5||nearby.min<712||nearby.max<=715.5)throw Error('Nearby context clipped');
await evaluate(`window.dispatchEvent(new KeyboardEvent('keydown',{key:'j'}))`);await waitFor(`document.body.textContent.includes('Trade 1 of 103 filtered trades')`);
await click('Close chart');
await evaluate(`document.querySelector('[aria-label="Select trade 1"]').click();var scopeSelect=document.querySelector('[aria-label="Export scope"]');scopeSelect.value='selected';scopeSelect.dispatchEvent(new Event('change',{bubbles:true}));`);
await waitFor(`document.body.textContent.includes('Export research pack (1)')`);
await click('Export research pack (1)');
await waitFor(`document.body.textContent.includes('Research Pack ready: 1 trades')`);
const captureFiles=async()=>evaluate(`Promise.all([...document.querySelectorAll('[aria-label="Research Pack export"] a[download]')].map(async a=>({name:a.download,size:(await(await fetch(a.href)).arrayBuffer()).byteLength,text:a.download.endsWith('.csv')?await(await fetch(a.href)).text():null})))`);
console.log('single',await captureFiles());
await screenshot('research-pack-single.png');
await evaluate(`var scopeSelect=document.querySelector('[aria-label="Export scope"]');scopeSelect.value='all';scopeSelect.dispatchEvent(new Event('change',{bubbles:true}));`);
await waitFor(`document.body.textContent.includes('Export research pack (103)')`);
await click('Export research pack (103)');await waitFor(`document.body.textContent.includes('Rendering #')`);await click('Cancel export');await waitFor(`document.body.textContent.includes('Cancelled after')`);
const started=Date.now();await send('Performance.enable');
await click('Export research pack (103)');
for(let i=0;i<150;i++){if(await evaluate(`document.body.textContent.includes('Research Pack ready: 103 trades')`))break;if(i%15===0)console.log('progress',await evaluate(`document.querySelector('[aria-label="Research Pack export"] [role="status"]').textContent`));await new Promise(r=>setTimeout(r,1000));}
await waitFor(`document.body.textContent.includes('Research Pack ready: 103 trades')`);
const files=await captureFiles();if(files.filter(f=>f.name.endsWith('.pdf')).length!==3)throw Error('Expected three PDFs');if(files.find(f=>f.name.endsWith('.csv')).text.split('\r\n').length!==104)throw Error('CSV row count');
console.log('large',files.map(({text,...rest})=>rest),'elapsed seconds',(Date.now()-started)/1000);
console.log('metrics',(await send('Performance.getMetrics')).metrics.filter(m=>['JSHeapUsedSize','JSHeapTotalSize','Nodes','Documents'].includes(m.name)));
console.log('history requests',await evaluate(`window.requests.filter(p=>p.endsWith('/review')).length`));
for(const width of [1024,1440,1920]){await send('Emulation.setDeviceMetricsOverride',{width,height:1080,deviceScaleFactor:1,mobile:false});await new Promise(r=>setTimeout(r,100));if(await evaluate(`document.documentElement.scrollWidth>innerWidth`))throw Error('Overflow '+width);}
if(process.env.LEDGER_SMOKE_OUTPUT){
 const length=await evaluate(`(async()=>{var link=document.querySelector('[aria-label="Research Pack export"] a[download]');window.pdfBytes=new Uint8Array(await(await fetch(link.href)).arrayBuffer());return window.pdfBytes.length})()`);
 const chunks=[];for(let offset=0;offset<length;offset+=65536){const chunk=await evaluate(`btoa(Array.from(window.pdfBytes.subarray(${offset},${offset+65536}),c=>String.fromCharCode(c)).join(''))`);chunks.push(Buffer.from(chunk,'base64'));}
 fs.writeFileSync(process.env.LEDGER_SMOKE_OUTPUT+'/research-pack.pdf',Buffer.concat(chunks));await evaluate('delete window.pdfBytes');
}

await evaluate(`window.failReview=true;var scopeSelect=document.querySelector('[aria-label="Export scope"]');scopeSelect.value='selected';scopeSelect.dispatchEvent(new Event('change',{bubbles:true}));`);
await waitFor(`document.body.textContent.includes('Export research pack (1)')`);await click('Export research pack (1)');await waitFor(`document.body.textContent.includes('Research Pack ready: 1 trades')`);
const degraded=await captureFiles();if(!degraded.find(f=>f.name.endsWith('.csv')).text.includes('Fixture history unavailable'))throw Error('Missing history not labelled');
console.log('PASS missing historical data exported with explicit warning');

if(errors.length)throw Error(errors.join('\n'));
console.log('PASS navigation, single PDF, cancellation, 103-trade PDF+CSV, three viewports, no runtime errors');close();
