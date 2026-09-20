import assert from 'node:assert/strict';
const base=process.env.LEDGER_SMOKE_URL;
assert(base&&['127.0.0.1','localhost'].includes(new URL(base).hostname));
const {send,evaluate,click,fill,waitFor,errors,close}=await import('./cdp.mjs');
const nav=text=>evaluate(`[...document.querySelectorAll('[aria-label="Main navigation"] button')].find(b=>b.textContent===${JSON.stringify(text)}).click()`);
const sub=(label,text)=>evaluate(`[...document.querySelectorAll('[aria-label="${label}"] button')].find(b=>b.textContent===${JSON.stringify(text)}).click()`);
const pause=()=>new Promise(r=>setTimeout(r,450));
const queue=await (await fetch(base+'/api/strategy-lab/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_key:crypto.randomUUID(),runs:['AAPL','NQ1!'].map(symbol=>({strategy_key:'opening_range_breakout_baseline_v1',symbols:[symbol],primary_timeframe:'1m',start_date:'2026-09-01',end_date:'2026-09-01',session:'auto',starting_balance:1000000,sizing_mode:'quantity',risk_value:1,allow_overnight:false,save_run:true,run_name:'CP12 acceptance '+symbol}))})})).json();assert.equal(queue.jobs?.length,2,JSON.stringify(queue));
await nav('Backtest');await sub('Backtest navigation','Backtest');await waitFor(`document.body.innerText.includes('Ready to run')`);await click('Show jobs');await waitFor(`document.querySelectorAll('[data-job-status="completed"]').length>=2`);
await sub('Backtest navigation','Runs');await waitFor(`document.querySelectorAll('[aria-label="Saved runs"] tbody tr').length>=2`);await evaluate(`(()=>{const boxes=[...document.querySelectorAll('[aria-label="Saved runs"] tbody input[type="checkbox"]')];boxes[0].click();boxes[1].click();})()`);await waitFor(`document.querySelector('.comparison-grid tbody tr')`);assert(await evaluate(`document.body.innerText.includes('No ranking or automatic winner')`));
await evaluate(`document.querySelector('[aria-label="Saved runs"] tbody .row-actions button').click()`);await waitFor(`document.body.innerText.includes('Execution assumptions:')`);console.log('PASS two independent queued runs, raw NQ execution, saved result, comparison');
const results=[];
for(const width of [1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
 for(const [page,tabs,aria] of [['Journal',['Trades','Analysis','Calendar','Daily Review','Playbook'],'Journal navigation'],['Backtest',['Backtest','Runs','Workspace'],'Backtest navigation']]){
  await nav(page);for(const tab of tabs){await sub(aria,tab);await pause();const w=await evaluate('({body:document.documentElement.scrollWidth,viewport:innerWidth})');assert(w.body<=w.viewport+1,JSON.stringify({width,tab,...w}));results.push({width,tab});}
 }
}
assert.equal(errors.length,0,errors.join('\n'));console.log('PASS 24 feature-subtab viewport checks',JSON.stringify(results));close();
