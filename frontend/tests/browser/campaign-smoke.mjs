import {send,evaluate,waitFor,click,errors,close,screenshot} from './cdp.mjs';
errors.length=0;
await send('Page.addScriptToEvaluateOnNewDocument',{source:`
localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Backtest'));
localStorage.setItem('ledger.ui.backtest.tab',JSON.stringify('Research Agent'));
window.launches=[];window.controls=[];
const policy={symbols:['QQQ'],timeframes:['1m'],directions:['long','short'],minimum_trades:30,holdout:'human_approval',budget:{wall_minutes:60,simulations:24,llm_calls:12,llm_usd:2},dataset:{}};
let campaign=null;
window.finishDevelopment=()=>{campaign.status='DEVELOPMENT_COMPLETE';campaign.execution.validation_contract={version:'one_generated_validation_v1'};campaign.validation={status:'ACTIVE',project_id:'p',validation_id:'v',validation_status:'ACTIVE',verdict:'PENDING'};};
window.fetch=async(url,opts={})=>{const path=new URL(String(url),location.origin).pathname;let data={items:[]};
if(path.endsWith('/strategies'))data={strategies:[{key:'fixture',name:'Fixture strategy',timeframes:['1m'],defaults:{},parameters:[]}]};
else if(path.endsWith('/validations/v/cancel-isolated')){campaign.validation={...campaign.validation,status:'COMPLETED',validation_status:'CANCELLED'};data=campaign.validation;}
else if(path.endsWith('/indicators'))data={indicators:[]};
else if(path.endsWith('/runs'))data={runs:[]};
else if(path.endsWith('/jobs'))data={jobs:[],max_workers:1,compute:{}};
else if(path.endsWith('/research-campaigns/policy'))data={defaults:policy,presets:{QUICK:policy,STANDARD:policy,DEEP:policy}};
else if(path.endsWith('/research-campaigns/launch')){const request=JSON.parse(opts.body);window.launches.push(request);campaign={id:'campaign-fixture',status:'ACTIVE',created_at:'2026-10-11',request:request.campaign,reserved:{llm_usd:0,simulations:1},plans:{},execution:{entries:[]}};data=campaign;}
else if(path.endsWith('/research-campaigns'))data={items:campaign?[campaign]:[]};
else if(path.includes('/research-campaigns/campaign-fixture')){
 if(opts.method==='POST'){const action=path.split('/').at(-1);window.controls.push(action);campaign.status=action==='pause'?'PAUSED':action==='resume'?'ACTIVE':'CANCELLED';data=campaign;}
 else data={campaign,worker:{running:true,error:null},summary:{baseline_runs_completed:1,numeric_cycles_completed:0,structural_checks_completed:0,holdout_consumed_by_campaign:false},events:[],morning_report:{families:[{project_id:'p',family_id:'vwap',state:'RUNNING',baseline_summary:{n:8,average_r:.2},verdict:'DEVELOPMENT_ONLY',warnings:['Low sample'],robustness:{cells:[{window:1,start:'2025-01-01',end:'2025-01-07',cost_multiplier:2,status:'COMPLETED',summary:{n:3,average_r:.1,total_r:.3,profit_factor_r:1.2}}]}}],conclusions:['No strategy automatically accepted.']}};
}
if(data.morning_report)Object.assign(data.morning_report.families[0],{structural_attempts:[{}],research_decision:{verdict:'INSUFFICIENT_EVIDENCE',reasons:['Sample below the frozen minimum.'],limitation:'Development only; holdout remains locked.'}});
if(data.morning_report)data.morning_report.families[0].search_history={debt:{structural_author_requests:2,structural_drafts:1,rejected_before_execution:0,failed_or_interrupted:1,numeric_hypotheses:1,numeric_variants_planned:3,integrity_errors:0},limitation:'Development search exposure only. Validation evidence is excluded.',records:[{id:'hypothesis',kind:'STRUCTURAL',status:'FAILED',preregistration:'VERIFIED',proposal:{description:'Avoid late entries',rationale:'Test continuation',feature:'One causal filter',expected_result:'Fewer entries',falsification:'Removed winners'},challenge:{concerns:['Small sample']},manager:{decision:'AUTHOR_CHILD',explanation:'Test only'},error:'duplicate_structural_source_no_retest'}]};
if(data.morning_report)data.morning_report.families[0].research_decision.simplification={verdict:'PREFER_SIMPLER_PARENT',limitation:'One generated feature only; not a significance test.',reasons:[],rows:[{scope:'full_period',cost_multiplier:1,parent_n:30,child_n:30,parent_average_r:.2,child_average_r:.2,delta_average_r:0}]};
if(data.morning_report&&campaign.status==='DEVELOPMENT_COMPLETE')data.morning_report.families[0].disposition={outcome:'ABANDONED_DEVELOPMENT',reasons:['No more structural attempts are scheduled under this campaign allocation.']};
return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}});};
`});
await send('Page.navigate',{url:process.env.LEDGER_SMOKE_URL||'http://127.0.0.1:19283'});
await waitFor(`document.querySelector('[aria-label="Autonomous research campaigns"]')`);
await waitFor(`document.body.textContent.includes('Ceilings:')`);
await evaluate(`(()=>{[...document.querySelectorAll('label')].find(l=>l.textContent.includes('Allow paid model review')).querySelector('input').click();})()`);
await waitFor(`document.body.textContent.includes('Allow structural research:')`);
await evaluate(`(()=>{[...document.querySelectorAll('label')].find(l=>l.textContent.includes('Allow structural research:')).querySelector('input').click();})()`);
await waitFor(`document.body.textContent.includes('Maximum structural attempts per family')`);
await evaluate(`(()=>{const el=[...document.querySelectorAll('label')].find(l=>l.textContent.includes('Maximum structural attempts')).querySelector('select');Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(el,'3');el.dispatchEvent(new Event('change',{bubbles:true}));})()`);
await evaluate(`(()=>{const el=document.querySelector('[aria-label="Campaign holdout policy"]');el.value='one_frozen_candidate';el.dispatchEvent(new Event('change',{bubbles:true}));})()`);
await waitFor(`document.body.textContent.includes('I authorize consuming one holdout')`);
await evaluate(`(()=>{const label=[...document.querySelectorAll('label')].find(l=>l.textContent.includes('I authorize these settings'));label.querySelector('input').click();})()`);
await click('Start campaign');
await waitFor(`document.body.textContent.includes('Backend coordinator running')`);
await waitFor(`document.body.textContent.includes('INSUFFICIENT EVIDENCE')&&document.body.textContent.includes('Sample below the frozen minimum.')`);
if(await evaluate(`window.launches.length!==1||window.launches[0].engine.sizing_mode!=='risk_pct'||window.launches[0].structural!==true||window.launches[0].campaign.policy.holdout!=='one_frozen_candidate'`))throw Error('Launch contract');
if(await evaluate(`window.launches[0].campaign.policy.max_structural_hypotheses_per_family!==3`))throw Error('Structural attempt limit lost');
await click('pause');await waitFor(`document.body.textContent.includes('PAUSED')`);
await click('resume');await waitFor(`document.body.textContent.includes('ACTIVE')`);
await evaluate('window.finishDevelopment()');
await waitFor(`document.body.textContent.includes('Policy-authorized validation: ACTIVE')`);
await waitFor(`document.body.textContent.includes('ABANDONED DEVELOPMENT')&&document.body.textContent.includes('Development closeout only.')`);
await click('Cancel candidate validation');await waitFor(`document.body.textContent.includes('CANCELLED')`);
await evaluate(`([...document.querySelectorAll('summary')].find(s=>s.textContent==='vwap: development windows and cost checks')).click()`);
await waitFor(`document.querySelector('[aria-label="vwap robustness samples"]')`);
if(await evaluate(`!document.querySelector('[aria-label="vwap robustness samples"]').textContent.includes('2025-01-01 to 2025-01-07')`))throw Error('Robustness sample dates missing');
await evaluate(`([...document.querySelectorAll('summary')].find(s=>s.textContent==='vwap: hypotheses and research debt')).click()`);
await waitFor(`document.body.textContent.includes('Falsified by: Removed winners')&&document.body.textContent.includes('2 structural requests')&&document.body.textContent.includes('duplicate_structural_source_no_retest')`);
await evaluate(`([...document.querySelectorAll('summary')].find(s=>s.textContent==='vwap: single-feature simplification')).click()`);
await waitFor(`document.querySelector('[aria-label="vwap feature ablation"]')&&document.body.textContent.includes('PREFER SIMPLER PARENT')`);
for(const width of [1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1080,deviceScaleFactor:1,mobile:false});
 await new Promise(r=>setTimeout(r,150));
 if(await evaluate(`document.documentElement.scrollWidth>innerWidth`))throw Error('Page overflow '+width);
 await screenshot('campaign-'+width+'.png');
 console.log('Campaign viewport passed',width);
}
await click('Advanced projects');await waitFor(`document.body.textContent.includes('deterministic foundation')`);
await click('Campaigns');await waitFor(`document.body.textContent.includes('Research report')`);
if(await evaluate(`window.launches.length!==1`))throw Error('Navigation relaunched campaign');
if(errors.length)throw Error(errors.join('\n'));
console.log('PASS: primary campaign UI, explicit settings/consent, launch, pause/resume, report, advanced navigation, three viewports, no runtime errors. Fixture API only.');
close();
