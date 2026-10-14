// Isolated deferred-response acceptance: no production APIs or saved results.
import {send,evaluate,waitFor,click,errors,close} from './cdp.mjs';
await send('Page.addScriptToEvaluateOnNewDocument',{source:`(()=>{
 localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Backtest'));
 localStorage.setItem('ledger.ui.backtest.tab',JSON.stringify('Runs'));
 const strategy={key:'race_fixture',name:'Race fixture',timeframes:['1m'],defaults:{},parameters:[]};
 window.pendingRuns={};
 window.fetch=async url=>{
  const path=new URL(String(url),location.origin).pathname;
  let data={items:[]};
  if(path.endsWith('/strategies'))data={strategies:[strategy]};
  else if(path.endsWith('/runs'))data={runs:[11,12,13].map(id=>({id,name:'Fixture '+id,strategy_key:strategy.key,strategy_name:strategy.name,symbols:['QQQ'],trades:0,tags:[],created_at:'2026-10-14',test_role:'development'}))};
  else if(path.endsWith('/jobs'))data={jobs:[],max_workers:1};
  else if(path.endsWith('/indicators'))data={indicators:[]};
  else if(path.endsWith('/research-experiments'))data={experiments:[]};
  else if(path.includes('/sections/')){
   const id=Number(path.split('/').at(-3));
   if(path.endsWith('/overview'))await new Promise(resolve=>window.pendingRuns[id]=resolve);
   data={id,name:'Fixture '+id,config:{strategy_key:strategy.key,symbols:['QQQ']},result:{strategy,symbols:['QQQ'],metrics:{trades:0},equity_curve:[],execution_model:{}}};
  }
  return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
 };
})()`});
await send('Page.navigate',{url:process.env.LEDGER_SMOKE_URL||'http://127.0.0.1:19383'});
await waitFor(`document.querySelector('tbody')?.textContent.includes('Fixture 13')`);
const open=id=>evaluate(`(()=>{const row=[...document.querySelectorAll('tbody tr')].find(r=>r.textContent.includes('Fixture ${id}'));[...row.querySelectorAll('button')].find(b=>b.textContent==='Open').click()})()`);
await open(11);await waitFor(`window.pendingRuns[11]`);
await click('Runs');await waitFor(`document.querySelector('tbody')?.textContent.includes('Fixture 12')`);
await open(12);await waitFor(`window.pendingRuns[12]`);
await evaluate(`window.pendingRuns[12]()`);
await waitFor(`document.querySelector('[aria-label="Run viewer sections"]')`);
await evaluate(`window.pendingRuns[11]()`);
await evaluate(`new Promise(resolve=>setTimeout(resolve,150))`);
const headings=await evaluate(`[...document.querySelectorAll('h1,h2,h3')].map(e=>e.textContent)`);
if(!headings.some(t=>t.includes('Fixture 12'))||headings.some(t=>t.includes('Fixture 11')))throw Error('Stale result replaced latest selection: '+headings.join('|'));
await click('Runs');await waitFor(`document.querySelectorAll('tbody tr').length===3`);
await open(13);await waitFor(`window.pendingRuns[13]`);
await click('Overview');
await evaluate(`window.pendingRuns[13]()`);
await evaluate(`new Promise(resolve=>setTimeout(resolve,150))`);
if(await evaluate(`!!document.querySelector('[aria-label="Run viewer sections"]')`))throw Error('Late result reopened unmounted viewer');
if(errors.length)throw Error(errors.join('\n'));
console.log('PASS: latest selected run wins; late response cannot reopen an unmounted viewer');
close();
