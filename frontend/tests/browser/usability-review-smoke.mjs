import {send,evaluate,waitFor,click,errors,close} from './cdp.mjs';
errors.length=0; // Ignore buffered exceptions from earlier documents; capture this navigation.
await send('Page.addScriptToEvaluateOnNewDocument',{source:`
localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Backtest'));localStorage.setItem('ledger.ui.backtest.tab',JSON.stringify('Backtest'));
window.requests=[];window.jobState='running';
const strategy={key:'smoke',name:'Review smoke',description:'Fixture',timeframes:['1m'],defaults:{length:2},parameters:[{key:'length',label:'Length',kind:'int',default:2,minimum:1,step:1}]};
const trade={symbol:'SPY',direction:'long',entry_time:'2026-09-28T13:34:00Z',exit_time:'2026-09-28T13:36:00Z',entry_price:106,exit_price:99,stop_loss:90,take_profit:120,net_pnl:-7,r_multiple:-.4,result:'loss',exit_reason:'strategy_exit',metadata:{}};
const result={strategy,metrics:{trades:1,starting_balance:10000,ending_balance:9993},symbols:['SPY'],primary_timeframe:'1m',session:'regular',equity_curve:[],execution_model:{}};
const config={strategy_key:'smoke',strategy_params:{length:2}};
window.fetch=async(url,opts={})=>{const path=new URL(String(url),location.origin).pathname;window.requests.push(path);let data={items:[]};
if(path.endsWith('/strategies'))data={strategies:[strategy]};
else if(path.endsWith('/indicators'))data={indicators:[]};
else if(path.endsWith('/jobs'))data={jobs:[{id:'one',batch_id:'batch',status:window.jobState,processed:1,total:2,run_id:1,payload:{run_name:'Smoke run',strategy_key:'smoke',symbols:['SPY']}}],max_workers:1,compute:{used_workers:0}};
else if(path.includes('/sections/')){await new Promise(r=>setTimeout(r,250));const section=path.split('/').at(-1);data={id:1,name:'Smoke run',created_at:'2026-09-28T14:00Z',config,section,result:section==='summary'?result:section==='trades'?{trades:[trade]}:{analysis:{},setups:[],rejected_signals:[]}};}
else if(path.endsWith('/review')){await new Promise(r=>setTimeout(r,250));const bars=Array.from({length:8},(_,i)=>({timestamp:new Date(Date.parse('2026-09-28T13:30Z')+i*60000).toISOString(),open:100+i,high:102+i,low:99+i,close:101+i,volume:100}));data={bars,symbol:'SPY',config,review:{series:[{id:'vwap',label:'VWAP',timeframe:'1m',overlay:true,role:'strategy_evidence',points:bars.map(b=>({timestamp:b.timestamp,available_at:new Date(Date.parse(b.timestamp)+60000).toISOString(),value:b.close-1}))}],levels:[],highlights:[{timestamp:bars[2].timestamp,kind:'entry'}],warnings:['Reconstructed fixture'],evidence:{entry:[{label:'Signal close',value:106,provenance:'recorded'}],exit:[{label:'Exit reason',value:'strategy_exit',provenance:'recorded'}]}}};}
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
if(await evaluate(`window.requests.some(p=>p.endsWith('/sections/trades'))`))throw Error('Trades eagerly fetched');
await evaluate(`document.querySelectorAll('[aria-label="Run viewer sections"] button')[1].click()`);
await waitFor(`document.body.textContent.includes('View chart')`);await click('View chart');
await waitFor(`document.body.textContent.includes('Why this trade entered')`);
await waitFor(`document.querySelector('canvas')`);
for(const width of [1024,1440,1920]){await send('Emulation.setDeviceMetricsOverride',{width,height:1080,deviceScaleFactor:1,mobile:false});await new Promise(r=>setTimeout(r,120));const overflow=await evaluate(`document.documentElement.scrollWidth>innerWidth`);if(overflow)throw Error('Overflow '+width);console.log('Trade Review viewport passed',width);}
await click('Close chart');
await evaluate(`window.jobState='completed';window.dispatchEvent(new Event('focus'))`);
await waitFor(`document.body.textContent.includes('Backtest completed')`);
await evaluate(`document.querySelector('button[aria-controls="ledger-activity"]').click()`);
await waitFor(`document.querySelector('[aria-label="Activity centre"]')`);
if(errors.length)throw Error(errors.join('\n'));
console.log('PASS: integrated sweep, no auto-open, immediate saved-run feedback, lazy trades, dynamic review, completion toast/activity, 3 viewports, no runtime errors');
close();
