// Run against an isolated Vite server and Chrome profile; ALL API traffic is mocked.
import assert from 'node:assert/strict';
const base=process.env.LEDGER_SMOKE_URL;
assert(base&&['127.0.0.1','localhost'].includes(new URL(base).hostname));
const {send,evaluate,click,waitFor,errors,close}=await import('./cdp.mjs');
function installFixtures(orbResearch=false) {
  localStorage.clear();localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Backtest'));localStorage.setItem('ledger.ui.backtest.tab',JSON.stringify('Runs'));
  const trades=Array.from({length:45},(_,i)=>({symbol:i<30?'TEST':'OTHER',direction:'long',entry_time:'2026-01-05T14:30:00Z',exit_time:'2026-01-05T14:40:00Z',entry_price:100,stop_loss:99,take_profit:102,exit_price:99,r_multiple:-1,net_pnl:-10,result:'loss',exit_reason:'stop_loss',planned_rr:2,metadata:i===0?{}:{mfe_r_lower_bound:1.86,mae_r:1,minutes_in_trade:10,time_to_1r:4,nested:{note:'a,"b"\nline'}}}));
  if(orbResearch)for(const trade of trades.slice(1))Object.assign(trade.metadata,{breakout_range:4,prior_1m_atr14:2,breakout_range_atr:2,breakout_body:2,breakout_body_ratio:.5,breakout_close_location:.75,breakout_volume:210,same_minute_volume_median20:105,breakout_rvol:2,opening_range_volume:1500,opening_range_volume_median20:15000,opening_range_rvol:.1,previous_daily_atr14:4,previous_close:100,daily_natr_pct:4,daily_natr_percentile:50});
  const result={strategy:{key:orbResearch?'opening_range_breakout_research_v1':'fixture',name:'Fixture'},symbols:['TEST','OTHER'],primary_timeframe:'1m',start:'2026-01-05',end:'2026-01-06',trades,metrics:{trades:45},equity_curve:[],analysis:{breakdowns:{}},data:{},execution_model:{},setups:[]};
  const saved={id:93,name:'Research fixture',config:{immutable:true,risk_value:123},result};
  const journal=trades.map((t,i)=>({id:i+1,ticker:t.symbol,direction:'long',opened_at:t.entry_time,closed_at:t.exit_time,r_multiple:-1,pnl_amount:-10,account_currency:'USD',account:'Fixture',source:'manual',status:'closed',result:'loss',notes:'=note',source_metadata:t.metadata,review_data:{custom:'kept'}}));
  window.fixtureSaved=saved;window.downloads=[];window.apiCalls=[];
  URL.createObjectURL=blob=>{const url='blob:fixture-'+window.downloads.length;window.downloads.push({blob,url});return url;};URL.revokeObjectURL=()=>{};
  HTMLAnchorElement.prototype.click=function(){const item=window.downloads.find(x=>x.url===this.href);if(item)item.filename=this.download;};
  window.fetch=async(url,options={})=>{
    const u=new URL(String(url),location.href),p=u.pathname;window.apiCalls.push(p);
    if(options.method && options.method!=='GET' && p!='/api/journal/report')throw Error('Unexpected mutation '+p);
    let body={};
    if(p==='/api/strategy-lab/runs')body={runs:[{id:93,name:saved.name,strategy_name:'Fixture',symbols:['TEST','OTHER'],trades:45,created_at:'2026-01-06'}]};
    else if(p==='/api/strategy-lab/runs/93')body=saved;
    else if(p.endsWith('/strategies'))body={strategies:[]};
    else if(p.endsWith('/indicators'))body={indicators:[]};
    else if(p.endsWith('/jobs'))body={jobs:[],max_workers:2};
    else if(p==='/api/strategy-workspace/files')body={files:[],template:'# fixture',default_filename:'_workspace_my_strategy.py'};
    else if(p.endsWith('/journal/settings'))body={timezone:'America/New_York'};
    else if(p.endsWith('/journal/playbooks'))body={items:[]};
    else if(p.endsWith('/journal/options'))body={};
    else if(p.endsWith('/journal/report')){const q=JSON.parse(options.body||'{}');body={trades:journal.filter(t=>!q.search||t.ticker.toLowerCase().includes(q.search.toLowerCase())),summary:{},breakdowns:{},timezone:'America/New_York'};}
    else if(p==='/api/portfolio')body={holdings:[{ticker:'TEST',quantity:1.25,average_cost:100,current_price:110,market_value:137.5}],transactions:Array.from({length:35},(_,id)=>({id,ticker:'TEST',quantity:1.25,price:100,asset_currency:'USD',base_currency:'GBP',account:'Fixture',action:'BUY',occurred_at:'2026-01-05',note:'kept'})),accounts:['Fixture'],base_currency:'GBP'};
    else if(p.endsWith('/broker-accounts'))body={items:[{account_key:'fixture-a',label:'Fixture A',summary:{currency:'GBP'}},{account_key:'fixture-b',label:'Fixture B',summary:{currency:'EUR'}}]};
    else if(p.endsWith('/broker-records'))body={total:35,items:Array.from({length:35},(_,id)=>({id,account_key:u.searchParams.get('account_key'),kind:u.searchParams.get('kind'),active:true,note:'kept',facts:{ticker:id<25?'TEST':'OTHER',quantity:1.25,averagePricePaid:100,currentPrice:110,instrument:{ticker:id<25?'TEST':'OTHER',currency:'USD'},walletImpact:{currency:'GBP',currentValue:137.5},order:{side:'BUY'},fill:{quantity:1.25,price:100},type:'DEPOSIT',amount:10,currency:'EUR'}}))};
    return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}});
  };
}
await send('Page.addScriptToEvaluateOnNewDocument',{source:`(${installFixtures.toString()})(${process.env.LEDGER_ORB_DIAGNOSTICS==='1'})`});
await send('Page.navigate',{url:base});
const download=async label=>{const before=await evaluate('downloads.length');await click(label);await waitFor(`downloads.length===${before+1}`);return evaluate(`downloads[${before}].blob.text()`);};
const nav=async text=>{await evaluate(`[...document.querySelectorAll('[aria-label="Main navigation"] button')].find(b=>b.textContent.trim()===${JSON.stringify(text)}).click()`);};
try {
  await waitFor(`document.querySelector('[aria-label="Saved runs"] tbody .row-actions button')`);
  await evaluate(`document.querySelector('[aria-label="Saved runs"] tbody .row-actions button').click()`);
  await waitFor(`document.querySelector('[aria-label="Run viewer sections"]')`);
  await click('Trades (45)');await waitFor(`document.body.innerText.includes('MFE (R)')`);
  assert.equal(await evaluate(`document.querySelectorAll('table tbody tr').length`),20);
  assert(await evaluate(`document.body.innerText.includes('2.86')`));
  const cells=await evaluate(`[...document.querySelectorAll('table tbody tr:first-child td')].map(x=>x.textContent)`);
  assert.equal(cells[11],'\u2014');assert.equal(cells[12],'\u2014');assert.equal(cells[13],'10.00');assert.equal(cells[14],'\u2014');
  const full=await download('Export all trades CSV');assert.equal((full.match(/"metadata_json"/g)||[]).length,1);assert.equal((full.match(/"stop_loss"/g)||[]).length,46);
  await evaluate(`(()=>{const label=[...document.querySelectorAll('label')].find(x=>x.textContent.startsWith('Symbol'));const el=label.querySelector('select');el.value='TEST';el.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  await waitFor(`document.body.innerText.includes('of 30 matching trades')`);
  const filtered=await download('Export filtered trades CSV');assert.equal((filtered.match(/"stop_loss"/g)||[]).length,31);
  assert.deepEqual(JSON.parse(await download('Export full run JSON')),await evaluate('fixtureSaved'));
  await click('Analysis');await waitFor(`document.body.innerText.includes('Excursion / trade management')`);assert(await evaluate(`document.body.innerText.includes('Low sample')`));
  if(process.env.LEDGER_ORB_DIAGNOSTICS==='1'){
    assert(await evaluate(`document.body.innerText.includes('ORB volatility / participation')`));
    assert.equal(await evaluate(`[...document.querySelectorAll('label')].find(x=>x.textContent.startsWith('Diagnostic bucket')).querySelectorAll('option').length`),16);
    assert.ok(full.includes('meta_breakout_rvol'));assert.ok(full.includes('meta_daily_natr_percentile'));
    console.log('PASS ORB research: 16 diagnostic bucket choices and scalar CSV fields');
  }
  for(const width of [1024,1440,1920]){await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});assert(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),`Analysis overflow at ${width}`);}
  console.log('PASS Run Viewer: legacy cells, all 45 / filtered 30 exports, immutable JSON, excursion analysis');
  await nav('Journal');await waitFor(`document.body.innerText.includes('Export matching trades CSV')`);
  const input=`document.querySelector('input[aria-label="Search Journal trades"]')`;
  await evaluate(`(()=>{const el=${input};Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'TEST');el.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  await waitFor(`document.body.innerText.includes('30 matching trades')`);
  const journal=await download('Export matching trades CSV');assert.ok(journal.includes('review_data'));assert.ok(journal.includes("'=note"));
  await evaluate(`[...document.querySelectorAll('[aria-label="Journal navigation"] button')].find(b=>b.textContent==='Analysis').click()`);
  await waitFor(`document.body.innerText.includes('Export filtered CSV')`);assert.equal(await download('Export filtered CSV'),journal);
  console.log('PASS Journal: filtered Trades and Analysis exports preserve notes and reviews');
  await nav('Portfolio');await waitFor(`document.body.innerText.includes('Export holdings CSV')`);
  const holdings=await download('Export holdings CSV');assert.ok(holdings.includes('price_currency'));assert.ok(holdings.includes('1.25'));
  const transactions=await download('Export transactions CSV');assert.equal((transactions.match(/"BUY"/g)||[]).length,35);
  await waitFor(`document.querySelector('[aria-label="Portfolio positions"] tbody tr')`);
  await evaluate(`(()=>{const el=document.querySelector('input[aria-label="Search Portfolio positions"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'TEST');el.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  await waitFor(`document.querySelector('[aria-label="Portfolio positions"] .table-count').textContent.includes('25')`);
  assert.equal(await evaluate(`document.querySelectorAll('[aria-label="Portfolio positions"] tbody tr').length`),20);
  const broker=await download('Export matching CSV');assert.equal((broker.match(/"fixture-a"/g)||[]).length,25);assert.ok(!broker.includes('[object Object]'));
  for(const label of ['Orders / fills','Dividends','Cash transactions']){await click(label);await waitFor(`!Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Export matching CSV').disabled`);const csv=await download('Export matching CSV');assert.ok(csv.includes('record_kind'));}
  await evaluate(`(()=>{const el=[...document.querySelectorAll('select')].find(x=>[...x.options].some(o=>o.value==='fixture-b'));el.value='fixture-b';el.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  await waitFor(`!Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Export matching CSV').disabled`);
  const accountB=await download('Export matching CSV');assert.equal((accountB.match(/"fixture-b"/g)||[]).length,35);assert.ok(!accountB.includes('fixture-a'));
  console.log('PASS Portfolio: raw holdings, all 35 transactions, filtered 25 broker positions, separate activity exports');
  assert.equal(errors.length,0,errors.join('\n'));console.log('PASS no runtime exceptions');
} finally {if(errors.length)console.error(errors);close();}
