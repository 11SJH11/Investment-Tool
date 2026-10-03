// All provider/API responses are mocked. No live Ledger data is used.
import assert from 'node:assert/strict';
const base=process.env.LEDGER_SMOKE_URL;assert(base&&new URL(base).hostname==='127.0.0.1');
const {send,evaluate,click,waitFor,errors,close}=await import('./cdp.mjs');
function fixtures(){
 localStorage.clear();localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Replay'));localStorage.setItem('ledger.chartTimeframe','1m');
 const all=Array.from({length:20},(_,i)=>({timestamp:new Date(Date.UTC(2026,8,1,13,30+i)).toISOString(),open:100+i,high:101+i,low:99+i,close:100.5+i,volume:1000}));
 window.failReplay=false;window.requests=[];
 window.fetch=async(url,options={})=>{
  const u=new URL(String(url),location.href),p=u.pathname;window.requests.push(p);let body={};
  if(p.endsWith('/replay/bars')){
   if(window.failReplay){const limited=window.failReplay==='rate';return new Response(JSON.stringify({detail:{category:limited?'rate_limited':'missing_history',message:limited?'Provider rate limited (HTTP 429). Retry no earlier than 2026-10-04T12:00:00+00:00.':'No usable history or dated contracts were returned for this range. Check symbol, dates and provider coverage.',retry_at:limited?'2026-10-04T12:00:00+00:00':null}}),{status:limited?429:503});}
   const frontier=u.searchParams.get('frontier');const count=frontier?all.findIndex(b=>b.timestamp===frontier)+1:2;
   body={timeline:all.map(b=>b.timestamp),bars:all.slice(0,count),source_bars:all.slice(0,count),initial_visible_count:2,visible_count:count,frontier:all[count-1].timestamp,replay_end_date:'2026-09-01',instrument:{asset_type:'stock'},provider:'fixture'};
  }else if(p.endsWith('/strategies'))body={strategies:[]};
  else if(p.endsWith('/indicators'))body={indicators:[]};
  else if(p.endsWith('/runs'))body={runs:[]};
  else if(p.endsWith('/jobs'))body={jobs:[],max_workers:1,compute:{used_workers:0}};
  else if(p.endsWith('/research-experiments'))body={experiments:[]};
  else if(p.includes('/watchlist'))body={items:[]};
  else if(p.includes('workspace'))body={files:[],strategies:[],template:'# fixture',default_filename:'_workspace_my_strategy.py'};
  else if(p.includes('/journal/trades'))body={id:1};
  return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}});
 };
}
await send('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixtures.toString()})()`});
await send('Page.navigate',{url:base+'/?guard='+Date.now()});
await waitFor(`document.body.innerText.includes('Load replay')`);errors.length=0;
const nav=label=>{assert.equal(errors.length,0,errors.join('\n'));return evaluate(`[...document.querySelectorAll('[aria-label="Main navigation"] button')].find(b=>b.textContent===${JSON.stringify(label)}).click()`);};
const guard=()=>waitFor(`document.querySelector('dialog[open]')`);
await click('Load replay');await waitFor(`document.querySelector('.replay-toolbar')`);
await click('BUY / LONG');
assert(await evaluate(`(()=>{const e=new Event('beforeunload',{cancelable:true});window.dispatchEvent(e);return e.defaultPrevented;})()`));
await nav('Backtest');await guard();
const count=await evaluate('requests.length');
await evaluate(`window.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}))`);
assert.equal(await evaluate('requests.length'),count,'Modal must suppress Replay shortcuts');
await click('Stay');
assert(await evaluate(`document.body.innerText.includes('Cancel order')`));
await nav('Backtest');await guard();
await evaluate(`window.originalSet=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(k==='ledger.replay.checkpoint')throw Error('quota');return originalSet.call(this,k,v);}`);
await click('Save checkpoint and leave');await waitFor(`document.querySelector('dialog [role="alert"]')`);
assert(await evaluate(`Boolean(document.querySelector('.replay-toolbar'))`));
assert.equal(await evaluate(`localStorage.getItem('ledger.replay.checkpoint')`),null);
await evaluate(`Storage.prototype.setItem=window.originalSet`);
await click('Save checkpoint and leave');await waitFor(`!document.querySelector('.replay-toolbar')&&!document.querySelector('dialog')`);
const pending=await evaluate(`JSON.parse(localStorage.getItem('ledger.replay.checkpoint'))`);assert(pending.pendingOrder);assert.equal(pending.anchorTimestamp,'2026-09-01T13:31:00.000Z');
await nav('Replay');await click('Resume saved replay');await waitFor(`document.body.innerText.includes('Checkpoint resumed.')`);
await click('Next bar');await waitFor(`document.body.innerText.includes('Close manually on next bar open')`);
await nav('Backtest');await guard();await click('Save checkpoint and leave');await waitFor(`!document.querySelector('dialog')`);
const active=await evaluate(`JSON.parse(localStorage.getItem('ledger.replay.checkpoint'))`);assert(active.position);assert.equal(active.anchorTimestamp,'2026-09-01T13:32:00.000Z');
await nav('Replay');await click('Resume saved replay');await waitFor(`document.body.innerText.includes('Close manually on next bar open')`);
await click('Close manually on next bar open');await click('Next bar');await waitFor(`document.body.innerText.includes('Saved to Journal')`);
await nav('Backtest');await guard();await click('Save checkpoint and leave');await waitFor(`!document.querySelector('dialog')`);
assert((await evaluate(`JSON.parse(localStorage.getItem('ledger.replay.checkpoint'))`)).closedTrade);
await nav('Replay');await evaluate(`window.failReplay=true`);await click('Resume saved replay');await waitFor(`document.body.innerText.includes('Could not resume checkpoint')`);
assert(!(await evaluate(`document.body.innerText.includes('Checkpoint resumed.')`)));
assert(await evaluate(`document.body.innerText.includes('No usable history or dated contracts')`));
await evaluate(`window.failReplay=false`);await click('Resume saved replay');await waitFor(`document.body.innerText.includes('Save closed trade to Journal')`);
await click('Next bar');await nav('Backtest');await guard();
for(const width of [1024,1440,1920]){await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`));}
const saved=await evaluate(`localStorage.getItem('ledger.replay.checkpoint')`);
await click('Leave / discard');await waitFor(`!document.querySelector('.replay-toolbar')&&!document.querySelector('dialog')`);
assert.equal(await evaluate(`localStorage.getItem('ledger.replay.checkpoint')`),saved);
await nav('Replay');await evaluate(`window.failReplay='rate'`);await click('Resume saved replay');await waitFor(`document.body.innerText.includes('Retry no earlier than 2026-10-04T12:00:00+00:00')`);
assert.equal(errors.length,0,errors.join('\n'));console.log('PASS Replay pending/active/closed trade checkpoints, Stay, quota failure, save/leave/resume, failed resume, discard, 1024/1440/1920 and runtime checks');close();
