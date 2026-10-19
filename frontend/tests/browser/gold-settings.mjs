// Opt-in mocked UI acceptance; no provider requests or order execution.
import assert from 'node:assert/strict';
const base=process.env.LEDGER_SMOKE_URL;
assert(base&&new URL(base).hostname==='127.0.0.1');
const {send,evaluate,waitFor,click,errors,close}=await import('./cdp.mjs');
function fixtures(){
 localStorage.clear();localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Backtest'));
 localStorage.setItem('ledger.ui.backtest.tab',JSON.stringify('Backtest'));
 const strategy={key:'gold_asia_15m_ifvg_research_v1',name:'Gold IFVG fixture',timeframes:['1m','15m'],defaults:{direction:'both'},parameters:[]};
 window.fetch=async(url,options={})=>{
  const path=new URL(String(url),location.href).pathname;let data={items:[]};
  if(path.endsWith('/strategies'))data={strategies:[strategy]};
  else if(path.endsWith('/runs'))data={runs:[]};
  else if(path.endsWith('/jobs')){if(options.method==='POST')window.submittedGold=JSON.parse(options.body);data={jobs:[],id:'fixture',max_workers:1};}
  else if(path.endsWith('/indicators'))data={indicators:[]};
  else if(path.endsWith('/research-experiments'))data={experiments:[]};
  return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
 };
}
await send('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixtures.toString()})()`});
await send('Page.navigate',{url:base+'/?gold-settings='+Date.now()});
await waitFor(`document.body.innerText.includes('XAUUSD')&&document.body.innerText.includes('Frictionless research')`);
assert(await evaluate(`document.body.innerText.includes('XAUUSD')`));
for(const [label,value] of [['Primary timeframe','1m'],['Market data session','auto']]){
 assert.equal(await evaluate(`(()=>{const label=[...document.querySelectorAll('label')].find(l=>l.querySelector('span')?.textContent.trim()===${JSON.stringify(label)});return label?.querySelector('select')?.value})()`),value);
}
assert(await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='Sun')?.className.includes('bg-stone-900')`));
assert(await evaluate(`[...document.querySelectorAll('button')].some(b=>b.textContent==='Sat')`));
await evaluate(`(()=>{for(const d of document.querySelectorAll('details'))d.open=true})()`);
for(const width of [1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
 assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Overflow '+width);
}
assert.equal(errors.length,0,errors.join('\n'));
console.log('PASS Gold 1m/auto, Sunday selected, seven weekdays, frictionless/risk disclosures; 1024/1440/1920');
close();
