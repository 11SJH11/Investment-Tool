// Isolated browser: all API requests are intercepted, no user/provider access.
import assert from 'node:assert/strict';
const base=process.env.LEDGER_SMOKE_URL;
assert(base&&new URL(base).hostname==='127.0.0.1');
const {send,evaluate,click,waitFor,errors,close}=await import('./cdp.mjs');
function fixtures(){
 localStorage.clear();localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Backtest'));
 localStorage.setItem('ledger.ui.backtest.tab',JSON.stringify('Backtest'));
 localStorage.setItem('ledger.ui.section.sensitivity-research','true');
 const parameters=[{key:'x',label:'ATR',kind:'float',default:-1,minimum:-1,maximum:5,step:.25},{key:'y',label:'RVOL',kind:'float',default:-1,minimum:-1,maximum:5,step:.25}];
 window.requests=[];let jobs=[],runs=[],plan=null,group='',experiment=null;
 window.finishResearch=()=>{if(experiment)experiment.status='failed';for(const job of jobs)job.status='failed';};
 window.fetch=async(url,options={})=>{
  const p=new URL(String(url),location.href).pathname;let body={};const payload=options.body?JSON.parse(options.body):null;
  requests.push({p,payload,search:new URL(String(url),location.href).search});
  if(p.endsWith('/strategies'))body={strategies:[{key:'fixture',name:'Fixture',timeframes:['1m'],parameters,defaults:{x:-1,y:-1}}]};
  else if(p.endsWith('/indicators'))body={indicators:[]};
  else if(p.endsWith('/jobs'))body={jobs,max_workers:4,compute:{configured_budget:4,used_workers:3,queued_simulations:17}};
  else if(p.endsWith('/compute-settings'))body={mode:'4',resolved_workers:4,configured_budget:4,used_workers:3,queued_simulations:17};
  else if(p.endsWith('/runs'))body={runs:runs.map(r=>({...r,result:undefined,strategy_name:'Fixture',symbols:['SPY']}))};
  else if(/\/runs\/\d+$/.test(p))body=runs.find(r=>r.id===Number(p.split('/').pop()));
  else if(p.endsWith('/status')&&p.includes('/experiments/'))body={experiment_group:group,status:experiment?.status||jobs[0]?.status,cells:(experiment?.cells||[]).map(c=>({...c,metrics:runs.find(r=>r.id===c.run_id)?.result.metrics}))};
  else if(p.includes('/experiments/'))body={experiment_group:group,runs,experiment,parent_job:jobs[0]};
  else if(p.endsWith('/research-experiments/preview')){
   const axes=payload.axes.map(a=>{const values=a.mode==='explicit'?a.values.split(',').map(Number):Array.from({length:Math.round((Number(a.end)-Number(a.start))/Number(a.step))+1},(_,i)=>Number(a.start)+i*Number(a.step));return {...parameters.find(p=>p.key===a.parameter),parameter:a.parameter,values,labels:values.map(String)};});
   const cells=axes.length===1?axes[0].values.map(v=>[v]):axes[0].values.flatMap(x=>axes[1].values.map(y=>[x,y]));
   plan={kind:axes.length===1?'spectrum':'interaction',axes,cells,job_count:cells.length};body=plan;
  }else if(p.endsWith('/research-experiments')&&(!options.method||options.method==='GET'))body={experiments:experiment?[experiment]:[]};
  else if(p.endsWith('/research-experiments')){
   group='research:'+payload.request_key;
   const childJobs=plan.cells.map((cell,i)=>({id:'j'+i,status:i===1?'failed':i===2?'running':'completed',run_id:100+i,error:i===1?'Fixture failure':null,payload:{...payload.base,experiment_group:group,research_experiment:{...plan,cell_index:i,cell}}}));
   runs=childJobs.filter(j=>j.status==='completed').map(j=>({id:j.run_id,name:payload.name,experiment_group:group,config:j.payload,result:{strategy:{key:'fixture',name:'Fixture'},symbols:['SPY'],primary_timeframe:'1m',trades:[],metrics:{trades:10,expectancy_r:-.1,total_r:-1,profit_factor_r:.8,max_drawdown_r:2,win_rate_pct:40},analysis:{},data:{},equity_curve:[],execution_model:{}}}));
   experiment={experiment_group:group,experiment_id:group,plan,name:payload.name,experiment_type:plan.kind,test_role:payload.role,base_configuration:payload.base,cells:childJobs.map((j,index)=>({index,status:j.status,run_id:j.run_id,error:j.error}))};
   jobs=[{id:'parent',batch_id:group,status:'running',processed:runs.length,total:plan.cells.length,payload:{...payload.base,run_name:payload.name,experiment_type:plan.kind,experiment_group:group,research_children:childJobs.map(j=>j.payload)}}];
   body={...plan,experiment_group:group,jobs};
  }else if(p.endsWith('/futures-preflight'))body={ready:false,reason:'Position sizing rounds to zero at the reference open under current full-notional leverage settings',warnings:[],limitations:['No CME/broker margin is assumed.']};
  else if(p.endsWith('/strategy-workspace/files'))body={files:[],template:'',default_filename:'_workspace_fixture.py'};
  return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}});
 };
}
await send('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixtures.toString()})()`});
await send('Page.navigate',{url:base});
const select=async(label,value)=>evaluate(`(()=>{const l=[...document.querySelectorAll('label')].find(l=>l.textContent.trim().startsWith(${JSON.stringify(label)}));const e=l.querySelector('select');e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
const input=async(label,value)=>evaluate(`(()=>{const l=[...document.querySelectorAll('label')].find(l=>l.textContent.trim().startsWith(${JSON.stringify(label)}));const e=l.querySelector('input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event('input',{bubbles:true}));})()`);
try{
 await waitFor(`document.body.innerText.includes('Preview exact values')`);
 await waitFor(`document.body.innerText.includes('CPU budget 4: 3 reserved, 17 simulations waiting')`);
 await waitFor(`document.querySelector('fieldset select')?.options.length===2`);
 await waitFor(`document.querySelector('fieldset').textContent.includes('Declared default: -1')`);
 await select('Values mode','range');await waitFor(`[...document.querySelectorAll('label')].some(l=>l.textContent==='start')`);await input('start','0');await input('end','1');await input('step','.25');
 await click('Preview exact values');await waitFor(`document.body.innerText.includes('5 exact backtests will be run.')`);
 assert(await evaluate(`document.body.innerText.includes('0, 0.25, 0.5, 0.75, 1')`));
 await click('Queue experiment');await waitFor(`document.querySelector('[aria-label="Exact parameter spectrum results"]')`);
 assert(await evaluate(`document.body.innerText.includes('Fixture failure')`));
 await evaluate(`[...document.querySelectorAll('[aria-label="Backtest navigation"] button')].find(b=>b.textContent==='Backtest').click()`);
 await select('Research mode','interaction');
 await evaluate(`(()=>{const fields=[...document.querySelectorAll('fieldset')].filter(f=>f.querySelector('legend')?.textContent.startsWith('Parameter'));for(const f of fields){const e=[...f.querySelectorAll('select')].find(e=>[...e.options].some(o=>o.value==='explicit'));e.value='explicit';e.dispatchEvent(new Event('change',{bubbles:true}));}})()`);
 await waitFor(`[...document.querySelectorAll('fieldset')].filter(f=>f.querySelector('legend')?.textContent.startsWith('Parameter')).every(f=>f.querySelectorAll('input').length===1)`);
 await evaluate(`(()=>{for(const f of [...document.querySelectorAll('fieldset')].filter(f=>f.querySelector('legend')?.textContent.startsWith('Parameter'))){const e=f.querySelector('input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,'-1, 1');e.dispatchEvent(new Event('input',{bubbles:true}));}})()`);
 await click('Preview exact values');await waitFor(`document.body.innerText.includes('4 exact backtests will be run.')`);await click('Queue experiment');
 await waitFor(`document.body.innerText.includes('zero-centred scale')`);
 assert(await evaluate(`document.body.innerText.includes('Low sample')`));
 assert(await evaluate(`document.body.innerText.includes('default control')`));
 assert.equal(await evaluate(`requests.filter(r=>r.p.endsWith('/research-experiments')&&r.payload).length`),2);
 assert.equal(await evaluate(`document.querySelectorAll('[aria-label="Backtest navigation"] button[aria-current="page"]')[0].textContent`),'Research Viewer');
 await select('Heatmap view','interaction');
 await waitFor(`document.body.innerText.includes('Interaction residual')`);
 for(const width of [1024,1440,1920]){await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});assert(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),`overflow at ${width}`);}
 await click('Open #103');await waitFor(`document.querySelector('[aria-label="Run viewer sections"]')`);
 assert(await evaluate(`requests.some(r=>r.p==='/api/strategy-lab/runs/103')`));
 assert(await evaluate(`requests.some(r=>r.p.endsWith('/status')&&r.p.includes('/experiments/'))`));
 assert(await evaluate(`requests.filter(r=>r.p.endsWith('/jobs')).every(r=>r.search==='?compact=true')`));
 assert.equal(errors.length,0,errors.join('\n'));
 console.log('PASS range preview, exact job count, partial failures, spectrum, 2D heatmap, low N/default, exact run opening, 1024/1440/1920 overflow and runtime checks');
}finally{if(errors.length)console.error(errors);close();}
