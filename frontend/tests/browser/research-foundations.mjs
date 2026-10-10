// Opt-in browser acceptance. All API traffic is mocked before application load.
import assert from 'node:assert/strict';
const base=process.env.LEDGER_SMOKE_URL;
assert(base&&new URL(base).hostname==='127.0.0.1');
const {send,evaluate,waitFor,click,errors,close}=await import('./cdp.mjs');
function fixtures(){
 localStorage.clear();localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Backtest'));
 window.researchCalls=[];let sandboxRun=null;let researchLoop=null,costReport=null,simplificationReport=null,regimeReport=null;const hypotheses=[];const reviews=[];const trials=[];const candidates=[];const validations=[];const decisions=[];window.researchAcceptanceScenario=()=>{decisions.length=0;validations[0].verdict='VALIDATION_PASS';};window.completeResearchTrial=()=>{trials[0].status="COMPLETED";trials[0].cells.forEach(c=>{c.status="COMPLETED";c.run_id=42+c.index;});};
 const project={id:'fixture',name:'Research fixture',state:'CREATED',strategy_key:'fixture',research_debt:{uses:0},datasets:[{id:'held2',symbols:['QQQ'],start:'2028-01-01',end:'2028-12-31',state:'LOCKED_HOLDOUT'},{id:'held',symbols:['QQQ'],start:'2025-01-01',end:'2025-12-31',state:'LOCKED_HOLDOUT'}],analyses:{},lineage:[],events:[]};
 window.fetch=async(url,options={})=>{
  const p=new URL(String(url),location.href).pathname;const method=options.method||'GET';researchCalls.push({path:p,method,body:options.body});let body={items:[]};
  if(p.endsWith('/strategies'))body={strategies:[{key:'fixture',name:'Fixture strategy',defaults:{skip:0},parameters:[{key:'skip',label:'Skip',kind:'int',default:0,minimum:0,maximum:1,step:1}],supported_timeframes:['1m']}]};
  else if(p.endsWith('/indicators'))body={indicators:[]};
  else if(p.endsWith('/runs'))body={runs:[]};
  else if(p.endsWith('/jobs'))body={jobs:[],compute:{mode:'1',configured_budget:1,used_workers:0}};
  else if(p.endsWith('/market-concepts'))body={items:[{key:'swing.strict.v1',scope:'canonical',status:'EXPERIMENTAL',description:'Previously confirmed strict pivots.',limitations:'Detection only',used_by:[],parameter_schema:{},dependencies:[],source_sha:'fixture'}]};
  else if(p.endsWith('/research-agent'))body={items:[project]};
  else if(p.endsWith('/code-drafts'))body={items:[{id:'draft',request:{registry_key:'research_child_smoke'},source_sha256:'abc123abc123'}]};
  else if(p.endsWith('/sandbox-runs'))body={items:sandboxRun?[sandboxRun]:[]};
  else if(p.endsWith('/code-drafts/draft/sandbox')){sandboxRun={id:'sandbox',candidate_id:'candidate',status:'RUNNING',phase:'CONTROL_PARITY'};body=sandboxRun;}
  else if(p.endsWith('/sandbox-runs/sandbox/cancel')){sandboxRun.status='CANCELLED';body=sandboxRun;}
  else if(p.endsWith('/manager-review'))body={action:'PLAN_COST_CHECK',reason:'Plan a declared cost check',minimum_new_runs:2,created_at:'2026-10-10',evidence:{runs_remaining:12,development_warnings:['Low sample']}};
  else if(p.endsWith('/candidates/candidate/regimes')){if(method==='POST')regimeReport={trial_id:'regimes',status:'COMPLETED',control_parity:true,request:JSON.parse(options.body),rows:[{name:'Fixture / baseline',status:'COMPLETED',summary:{n:2,average_r:1,total_r:2,low_sample:true}},{name:'Fixture / candidate',status:'COMPLETED',summary:{n:1,average_r:.5,total_r:.5,low_sample:true}}],limitation:'Independent windows, no stitched portfolio performance'};body=regimeReport;}
  else if(p.endsWith('/simplification-suggestions'))body={scenarios:[{name:'Suggested toggle',parameter:'skip',off_value:1,rule_removed:'Mock declared off value; user must verify'}],rationale:'Mock declaration-only suggestion'};
  else if(p.endsWith('/candidates/candidate/costs')){if(method==='POST')costReport={trial_id:'cost',status:'COMPLETED',control_parity:true,rows:[{name:'Frozen candidate control',status:'COMPLETED',summary:{n:2,average_r:1,profit_factor_r:2},money:{gross_pnl:100,fees:0,net_pnl:100}},{name:'Declared stress',status:'COMPLETED',summary:{n:2,average_r:.8,profit_factor_r:1.5},money:{gross_pnl:100,fees:20,net_pnl:80}}],limitation:'Development engine reruns only'};body=costReport;}
  else if(p.endsWith('/candidates/candidate/simplification')){if(method==='POST')simplificationReport={trial_id:'simplification',status:'COMPLETED',control_parity:true,request:JSON.parse(options.body),rows:[{name:'Frozen candidate control',status:'COMPLETED',summary:{n:2,average_r:1,total_r:2,profit_factor_r:2}},{name:'Disable fixture rule',status:'COMPLETED',summary:{n:3,average_r:.5,total_r:1.5,profit_factor_r:1.5},removed_winners:{n:1},removed_large_winners:{n:0},introduced:{n:2}}],limitation:'Development single-parameter ablations only'};body=simplificationReport;}
  else if(p.endsWith('/decisions'))body={items:decisions};
  else if(p.endsWith('/candidates/candidate/decision')){const d={candidate_id:'candidate',decision:JSON.parse(options.body).decision,request:JSON.parse(options.body)};decisions.push(d);body=d;}
  else if(p.endsWith('/validations'))body={items:validations};
  else if(p.endsWith('/candidates/candidate/validate')){const v={id:'validation',candidate_id:'candidate',status:'COMPLETED',verdict:'INSUFFICIENT_EVIDENCE',criteria:JSON.parse(options.body).criteria};validations.push(v);project.datasets.find(d=>d.id===JSON.parse(options.body).dataset_id).state='INSPECTED_VALIDATION';body=v;}
  else if(p.endsWith('/candidates/assess'))body={summary:{n:2,average_r:1,total_r:2},verdict:'VALIDATION_REQUIRED',warnings:['Low sample','Incomplete neighborhood'],neighbor_coverage:[{parameter:'fixture',side:'lower',tested:false,value:null}],neighbors:[],periods:{year:[]}};
  else if(p.endsWith('/candidates')){if(method==='POST'){const candidate={id:'candidate',run_id:43,state:'FROZEN',reason:JSON.parse(options.body).reason};candidates.push(candidate);if(researchLoop){researchLoop.status='STOPPED';researchLoop.reason='Candidate frozen';}body=candidate;}else body={items:candidates};}
  else if(p.endsWith('/loop')){if(method==='POST')researchLoop={id:'loop',status:'ACTIVE',phase:'REVIEW',max_cycles:JSON.parse(options.body).max_cycles,cycles:[]};body=researchLoop;}
  else if(p.endsWith('/loop/pause')||p.endsWith('/loop/resume')){researchLoop.status=p.endsWith('/pause')?'PAUSED':'ACTIVE';body=researchLoop;}
  else if(p.endsWith('/trials'))body={items:trials,reserved_runs:trials.length*4,budget:{max_trial_runs:80}};
  else if(p.includes('/hypotheses/')&&p.endsWith('/approve')){const trial={id:'trial',status:'ACTIVE',hypothesis:{description:'Approved fixture'},cells:[{index:0,role:'control',status:'COMPLETED'},{index:1,role:'variant',status:'PENDING'}],control_parity:true,verdict:'PENDING'};trials.push(trial);body=trial;}
  else if(p.includes('/trials/trial/')){trials[0].status=p.endsWith('/pause')?'PAUSED':p.endsWith('/resume')?'ACTIVE':'CANCELLED';body=trials[0];}
  else if(p.endsWith('/committee')){
   if(method==='POST'){const review={id:'review',status:'COMPLETED',created_at:'2026-10-08',roles:{Researcher:{description:'Committee proposal'},Devil:{concerns:['Small sample']},Manager:{decision:'RECOMMEND_EXPERIMENT'}},evidence:{summary:{n:1}},usage:{}};reviews.push(review);body=review;}
   else body={items:reviews,model:{configured:true,model:'mock-model'},reserved_calls:reviews.length*3,max_calls:12,reserved_cost_usd:reviews.length*.3,max_spend_usd:10};
  }
  else if(p.endsWith('/committee/review/preregister')){const h={id:'committee-hypothesis',description:'Committee proposal',status:'PREREGISTERED',plan:{job_count:1}};hypotheses.push(h);body=h;}
  else if(p.endsWith('/hypotheses')){
   if(method==='POST'){const h={...JSON.parse(options.body),id:'hypothesis',status:'PREREGISTERED',plan:{job_count:3}};hypotheses.push(h);body=h;}else body={items:hypotheses};
  }
  else if(p.includes('/research-agent/fixture')){
   if(method==='GET'&&project.state==='BASELINE_RUNNING'){project.state='BASELINE_ANALYSIS';project.baseline_run_id=1;project.analyses={'1':{summary:{n:1,total_r:2,mfe_n:1,average_mfe_r:3,mfe_lower_bound_n:0,mae_n:0,average_mae_r:null},warnings:['Low sample'],day_basis:'New York calendar entry date',large_winner_threshold_r:2,large_winners:{n:1},session_close_winners:{n:1},breakdowns:{entry_hour:{'10':{n:1,average_r:2,total_r:2,profit_factor_r:null,win_rate_pct:100,average_mfe_r:3,average_mae_r:null,low_sample:true}}}}};}
   if(p.endsWith('/state'))project.state=JSON.parse(options.body).state==='BASELINE_ANALYSIS'?'CREATED':JSON.parse(options.body).state;
   if(p.endsWith('/approve'))project.datasets[0].state='INSPECTED_VALIDATION';
   if(p.endsWith('/baseline')){project.state='BASELINE_RUNNING';project.baseline_job_id='one';}
   body=project;
  }
  return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}});
 };
}
await send('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixtures.toString()})()`});
await send('Page.navigate',{url:base+'/?research-smoke='+Date.now()});
await waitFor(`document.body.innerText.includes('Market Concepts')`);
await click('Market Concepts');await waitFor(`document.body.innerText.includes('swing.strict.v1')`);
assert(await evaluate(`document.body.innerText.includes('None yet; no inferred equivalence')`));
await click('Research Agent');await waitFor(`document.body.innerText.includes('Research fixture / CREATED')`);
await click('Research fixture / CREATED');await waitFor(`document.body.innerText.includes('Queue frozen baseline')`);
assert(await evaluate(`!researchCalls.some(c=>c.method==='POST')`));
await evaluate(`window.confirm=()=>false`);await click('Approve holdout inspection');
assert(await evaluate(`!researchCalls.some(c=>c.path.endsWith('/approve'))`));
await evaluate(`window.confirm=()=>true`);await click('Approve holdout inspection');
await waitFor(`document.body.innerText.includes('INSPECTED_VALIDATION')`);
assert(await evaluate(`JSON.parse(researchCalls.find(c=>c.path.endsWith('/approve')).body).acknowledgement==='This dataset will no longer be unseen'`));
await click('Pause');await waitFor(`document.body.innerText.includes('Research fixture / PAUSED')`);
await click('Resume');await waitFor(`document.body.innerText.includes('Queue frozen baseline')`);
for(const width of [1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
 assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Research overflow '+width);
}
await click('Queue frozen baseline');await waitFor(`document.body.innerText.includes('BASELINE_RUNNING')`);
assert(await evaluate(`researchCalls.filter(c=>c.path.endsWith('/baseline')).length===1`));
await waitFor(`document.body.innerText.includes('Preregister a controlled parameter experiment')`);
await evaluate(`[...document.querySelectorAll('summary')].find(x=>x.textContent==='Winner retention, excursions and diagnostic breakdowns').click()`);
assert(await evaluate(`document.body.innerText.includes('MFE 3.00R (N 1')&&document.body.innerText.includes('MAE UnavailableR (N 0')`));
await evaluate(`[...document.querySelectorAll('summary')].find(x=>x.textContent==='entry hour').click()`);
assert(await evaluate(`document.body.innerText.includes('10 / Low sample')`));
await evaluate(`(()=>{const summary=[...document.querySelectorAll('summary')].find(x=>x.textContent==='Preregister a controlled parameter experiment');summary.click();const labels=[...summary.parentElement.querySelectorAll('label')];for(const label of labels){const el=label.querySelector('textarea,input:not([type=checkbox])');if(!el)continue;const value=label.textContent.includes('Exact values')?'1,2,3':label.textContent.includes('Declared numeric')?'fixture_parameter':'Synthetic hypothesis';Object.getOwnPropertyDescriptor(el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(el,value);el.dispatchEvent(new Event('input',{bubbles:true}));}summary.parentElement.querySelector('input[type=checkbox]').click();})()`);
await click('Preregister hypothesis');await waitFor(`document.body.innerText.includes('PREREGISTERED / 3 variants')`);
assert(await evaluate(`researchCalls.filter(c=>c.method==='POST'&&c.path.endsWith('/hypotheses')).length===1`));
assert(await evaluate(`!researchCalls.some(c=>c.path.includes('/hypotheses/')&&c.path.endsWith('/approve'))`));
await evaluate(`[...document.querySelectorAll('summary')].find(s=>s.textContent.includes('Synthetic hypothesis / PREREGISTERED')).click()`);
await click('Approve development trial');await waitFor(`document.body.innerText.includes('Approved fixture / ACTIVE')`);
assert(await evaluate(`document.body.innerText.includes('Control parity: Verified')`));
for(const width of [1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
 assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Trial table overflow '+width);
}
await click('Pause trial');await waitFor(`document.body.innerText.includes('Approved fixture / PAUSED')`);
await evaluate(`[...document.querySelectorAll('summary')].find(s=>s.textContent.includes('Approved fixture / PAUSED')).click()`);
await click('Resume trial');await waitFor(`document.body.innerText.includes('Approved fixture / ACTIVE')`);
assert(await evaluate(`researchCalls.filter(c=>c.path.includes('/hypotheses/')&&c.path.endsWith('/approve')).length===1`));
assert(await evaluate(`!researchCalls.some(c=>c.path.endsWith('/committee')&&c.method==='POST')`));
assert(await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='Run committee review').disabled`));
assert(await evaluate(`document.body.innerText.includes('Reserved estimate: $0 / $10')`));
await evaluate(`[...document.querySelectorAll('label')].find(l=>l.textContent.includes('I agree to send')).querySelector('input').click()`);
await click('Run committee review');await waitFor(`document.body.innerText.includes('COMPLETED / RECOMMEND_EXPERIMENT')`);
await evaluate(`[...document.querySelectorAll('summary')].find(s=>s.textContent.includes('COMPLETED / RECOMMEND_EXPERIMENT')).click()`);
assert(await evaluate(`!researchCalls.some(c=>c.path.endsWith('/committee/review/preregister'))`));
await click('Preregister recommendation');await waitFor(`document.body.innerText.includes('Committee proposal / PREREGISTERED / 1 variants')`);
assert(await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='Start bounded research loop').disabled`));
assert(await evaluate(`!researchCalls.some(c=>c.path.endsWith('/loop')&&c.method==='POST')`));
await evaluate(`[...document.querySelectorAll('label')].find(l=>l.textContent.includes('Authorize sending development summaries')).querySelector('input').click()`);
await click('Start bounded research loop');await waitFor(`document.body.innerText.includes('ACTIVE / REVIEW / 0 of 1')`);
assert(await evaluate(`JSON.parse(researchCalls.find(c=>c.path.endsWith('/loop')&&c.method==='POST').body).acknowledgement==='Authorize bounded model reviews and development backtests'`));
await click('Pause research loop');await waitFor(`document.body.innerText.includes('PAUSED / REVIEW')`);
await click('Resume research loop');await waitFor(`document.body.innerText.includes('ACTIVE / REVIEW')`);
for(const width of [1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
 assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Loop overflow '+width);
}
await evaluate(`window.completeResearchTrial()`);
await waitFor(`document.querySelector('[aria-label="Candidate development variant"]').options.length>1`);
await evaluate(`(()=>{const el=document.querySelector('[aria-label="Candidate development variant"]');Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(el,el.options[1].value);el.dispatchEvent(new Event('change',{bubbles:true}));})()`);
await click('Inspect candidate robustness');await waitFor(`document.body.innerText.includes('VALIDATION_REQUIRED')`);
assert(await evaluate(`document.body.innerText.includes('Not tested')`));
assert(await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='Freeze candidate').disabled`));
await evaluate(`(()=>{const el=[...document.querySelectorAll('label')].find(l=>l.textContent==='Candidate rationale').querySelector('textarea');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(el,'Investigate robustness');el.dispatchEvent(new Event('input',{bubbles:true}));[...document.querySelectorAll('label')].find(l=>l.textContent.includes('Freeze this development candidate;')).querySelector('input').click();})()`);
await click('Freeze candidate');await waitFor(`document.body.innerText.includes('Run 43 / FROZEN')`);
await waitFor(`document.body.innerText.includes('Candidate frozen')`);
assert(await evaluate(`researchCalls.filter(c=>c.path.endsWith('/candidates')&&c.method==='POST').length===1`));
await evaluate(`[...document.querySelectorAll('summary')].find(s=>s.textContent.includes('Run 43 / FROZEN')).click()`);
assert(await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='Approve and run candidate validation').disabled`));

await evaluate(`[...document.querySelectorAll('summary')].find(s=>s.textContent==='Manager next-step review').click()`);
await click('Review next research step');await waitFor(`document.body.innerText.includes('PLAN COST CHECK')`);
assert(await evaluate(`!researchCalls.some(c=>c.path.endsWith('/regimes')&&c.method==='POST')`));
await evaluate(`[...document.querySelectorAll('summary')].find(s=>s.textContent==='Development regime robustness').click()`);
assert(await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='Approve regime robustness trial').disabled`));
await evaluate(`(()=>{for(const [label,value] of [['Regime name','Fixture'],['Start date','2026-01-02'],['End date','2026-01-02'],['Numerical definition / market conditions','Synthetic known fixture'],['Evidence source for the classification','Fixed fixture'],['Regime study rationale','Paired comparison']]){const el=[...document.querySelectorAll('label')].find(l=>l.textContent.startsWith(label)).querySelector('input,textarea');Object.getOwnPropertyDescriptor(el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(el,value);el.dispatchEvent(new Event('input',{bubbles:true}));}[...document.querySelectorAll('label')].find(l=>l.textContent.includes('Run these development windows;')).querySelector('input').click();})()`);
await click('Approve regime robustness trial');await waitFor(`document.body.innerText.includes('Fixture / candidate')`);
assert(await evaluate(`researchCalls.filter(c=>c.path.endsWith('/regimes')&&c.method==='POST').length===1`));
await evaluate(`[...document.querySelectorAll('summary')].find(s=>s.textContent==='Engine cost robustness').click()`);
assert(await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='Approve cost robustness trial').disabled`));
await evaluate(`(()=>{for(const [label,value] of [['Commission per order','5'],['Cost assumptions and rationale','Synthetic declared commission stress']]){const el=[...document.querySelectorAll('label')].find(l=>l.textContent.startsWith(label)).querySelector('input,textarea');Object.getOwnPropertyDescriptor(el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(el,value);el.dispatchEvent(new Event('input',{bubbles:true}));}[...document.querySelectorAll('label')].find(l=>l.textContent.includes('Run the frozen candidate control and declared cost scenarios')).querySelector('input').click();})()`);
await click('Approve cost robustness trial');await waitFor(`document.body.innerText.includes('Gross P&L')&&document.body.innerText.includes('80.00')`);
assert(await evaluate(`researchCalls.filter(c=>c.path.endsWith('/candidates/candidate/costs')&&c.method==='POST').length===1`));
for(const width of [1024,1440,1920]){await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Cost table overflow '+width);}

await evaluate(`(()=>{const el=document.querySelector('[aria-label="Candidate validation dataset"]');Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(el,el.options[1].value);el.dispatchEvent(new Event('change',{bubbles:true}));[...document.querySelectorAll('label')].find(l=>l.textContent.includes('I approve consuming this dataset')).querySelector('input').click();})()`);

await evaluate(`[...document.querySelectorAll('summary')].find(s=>s.textContent==='Single-rule simplification tests').click()`);
assert(await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='Approve simplification trial').disabled`));
await click('Suggest declared rule ablations');await waitFor(`[...document.querySelectorAll('input')].some(x=>x.value==='Suggested toggle')`);
assert(await evaluate(`!researchCalls.some(c=>c.path.endsWith('/simplification')&&c.method==='POST')`));
await evaluate(`(()=>{const el=[...document.querySelectorAll('label')].find(l=>l.textContent.startsWith('Rule parameter')).querySelector('select');Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(el,'skip');el.dispatchEvent(new Event('change',{bubbles:true}));})()`);
await waitFor(`document.body.innerText.includes('Frozen effective value: 0')`);
await evaluate(`(()=>{for(const [label,value] of [['Ablation name','Disable fixture rule'],['Declared off value','1'],['Rule removed and why this value disables it','Synthetic fixture toggle disables the rule'],['Simplification rationale','Test single rule removal without changing costs']]){const el=[...document.querySelectorAll('label')].find(l=>l.textContent.startsWith(label)).querySelector('input,textarea');Object.getOwnPropertyDescriptor(el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(el,value);el.dispatchEvent(new Event('input',{bubbles:true}));}})()`);
assert(await evaluate(`!researchCalls.some(c=>c.path.endsWith('/candidates/candidate/simplification')&&c.method==='POST')`));
await evaluate(`[...document.querySelectorAll('label')].find(l=>l.textContent.includes('I verified these off values;')).querySelector('input').click()`);
await click('Approve simplification trial');await waitFor(`document.body.innerText.includes('Declared removals, parameters and saved evidence')`);
assert(await evaluate(`researchCalls.filter(c=>c.path.endsWith('/candidates/candidate/simplification')&&c.method==='POST').length===1`));
for(const width of [1024,1440,1920]){await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Simplification table overflow '+width);}

await waitFor(`document.body.innerText.includes('Quarantined strategy sandbox')`);
assert(await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='Run isolated checks').disabled`));
await evaluate(`(()=>{const el=[...document.querySelectorAll('label')].find(l=>l.textContent.startsWith('Quarantined draft')).querySelector('select');Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(el,'draft');el.dispatchEvent(new Event('change',{bubbles:true}));})()`);
await evaluate(`[...document.querySelectorAll('label')].find(l=>l.textContent.includes('Approve Docker execution')).querySelector('input').click()`);
await click('Run isolated checks');await waitFor(`document.body.innerText.includes('RUNNING / CONTROL_PARITY')`);
assert(await evaluate(`researchCalls.filter(c=>c.path.endsWith('/sandbox')&&c.method==='POST').length===1`));
for(const width of [1024,1440,1920]){await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Sandbox overflow '+width);}
await click('Cancel isolated run');await waitFor(`document.body.innerText.includes('CANCELLED / CONTROL_PARITY')`);
await click('Approve and run candidate validation');await waitFor(`document.body.innerText.includes('COMPLETED / INSUFFICIENT_EVIDENCE')`);
await waitFor(`!document.body.innerText.includes('LOCKED_HOLDOUT')`);
assert(await evaluate(`researchCalls.filter(c=>c.path.endsWith('/candidates/candidate/validate')&&c.method==='POST').length===1`));
assert(await evaluate(`document.querySelector('[aria-label="Candidate research decision"]').options[1].disabled`));
assert(await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='Record research decision').disabled`));
await evaluate(`(()=>{const el=[...document.querySelectorAll('label')].find(l=>l.textContent==='Decision rationale').querySelector('textarea');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(el,'Insufficient validation evidence');el.dispatchEvent(new Event('input',{bubbles:true}));[...document.querySelectorAll('label')].find(l=>l.textContent.includes('Record this final research decision;')).querySelector('input').click();})()`);
await click('Record research decision');await waitFor(`document.body.innerText.includes('REJECTED')`);
assert(await evaluate(`researchCalls.filter(c=>c.path.endsWith('/candidates/candidate/decision')&&c.method==='POST').length===1`));
assert(await evaluate(`document.body.innerText.includes('Saved validation evidence')`));
// Independent accepted-candidate UI scenario; persistence/immutability is verified by backend tests.
await evaluate(`window.researchAcceptanceScenario()`);
await click('Market Concepts');await waitFor(`document.body.innerText.includes('swing.strict.v1')`);
await click('Research Agent');await waitFor(`document.body.innerText.includes('Research fixture / BASELINE_ANALYSIS')`);
await click('Research fixture / BASELINE_ANALYSIS');await waitFor(`document.body.innerText.includes('Run 43 / FROZEN')`);
await evaluate(`[...document.querySelectorAll('summary')].find(s=>s.textContent.includes('Run 43 / FROZEN')).click()`);
await waitFor(`document.querySelector('[aria-label="Candidate research decision"]')&&!document.querySelector('[aria-label="Candidate research decision"]').options[1].disabled`);
await evaluate(`(()=>{const el=document.querySelector('[aria-label="Candidate research decision"]');Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(el,'ACCEPTED_FOR_RESEARCH');el.dispatchEvent(new Event('change',{bubbles:true}));})()`);
assert(await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='Record research decision').disabled`));
await evaluate(`(()=>{for(const text of ['Decision rationale','Period consistency','Winner retention and changed paths','Parameter neighborhood','Costs and market regimes','Complexity, missing checks and limitations']){const el=[...document.querySelectorAll('label')].find(l=>l.textContent===text).querySelector('textarea');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(el,'Reviewed synthetic evidence; missing checks remain limitations');el.dispatchEvent(new Event('input',{bubbles:true}));}[...document.querySelectorAll('label')].find(l=>l.textContent.includes('Record this final research decision;')).querySelector('input').click();})()`);
await click('Record research decision');await waitFor(`document.body.innerText.includes('ACCEPTED_FOR_RESEARCH')`);
assert(await evaluate(`researchCalls.filter(c=>c.path.endsWith('/candidates/candidate/decision')&&c.method==='POST').length===2`));



for(const width of [1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
 assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Candidate overflow '+width);
}
await click('Market Concepts');await waitFor(`document.body.innerText.includes('swing.strict.v1')`);
for(const width of [1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
 assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Concept overflow '+width);
}
assert.equal(errors.length,0,errors.join('\n'));
console.log('PASS research/concept navigation, explicit approval/cancel, pause/resume, single baseline submission, recorded/missing diagnostics, hypothesis registration, explicit trial approval/pause/resume, consent-gated committee and explicit recommendation preregistration, explicit bounded-loop authorization/pause/resume, monetary reservation display, candidate robustness/consent/freeze/loop stop/cost approval and gross-net evidence/single-rule ablation approval and evidence/explicit validation/research rejection/structured research acceptance, no mutation before consent, 1024/1440/1920 overflow and runtime checks.');
close();
