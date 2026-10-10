// Opt-in isolated browser test; all backend traffic is mocked.
import assert from 'node:assert/strict';
const base=process.env.LEDGER_SMOKE_URL;
assert(base&&new URL(base).hostname==='127.0.0.1');
const {send,evaluate,waitFor,click,errors,close}=await import('./cdp.mjs');
function fixtures(){
 localStorage.clear();localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Backtest'));
 window.auditCalls=[];const items=[];
 const bars=Array.from({length:20},(_,i)=>({timestamp:new Date(Date.UTC(2026,0,2,14,30+i)).toISOString(),open:100,high:102,low:99,close:101,volume:10}));
 const report={timeframe:'1m',bar_count:20,observation_count:1,causality:{status:'PASS',probes:[]},confirmation_lag_seconds:{median:180},zone_size_midpoint_bps:{median:null},followup:{complete_observations:1,right_censored_observations:0,upward_bps:{mean:100},downward_bps:{mean:-200},complete_zones:0,touched_complete_zones:0},sample_policy:'Fixed deterministic sample, not selected by outcome.',examples:[{index:0,observation:{label:'Swing high',occurred_at:bars[3].timestamp,confirmed_at:bars[6].timestamp},bars,overlays:[{label:'Confirmed swing',values:bars.slice(6).map(b=>({timestamp:b.timestamp,value:102}))}],followup:{complete_horizon:true}}]};
 window.fetch=async(url,options={})=>{const p=new URL(String(url),location.href).pathname;const method=options.method||'GET';auditCalls.push({path:p,method,body:options.body});let body={items:[]};
 if(p.endsWith('/strategies'))body={strategies:[]};
 else if(p.endsWith('/indicators'))body={indicators:[]};
 else if(p.endsWith('/runs'))body={runs:[]};
 else if(p.endsWith('/jobs'))body={jobs:[]};
 else if(p.endsWith('/market-concepts'))body={items:[{key:'swing.strict.v1',scope:'canonical',status:'EXPERIMENTAL',description:'Strict pivots',limitations:'Detection only',used_by:[],dependencies:[],parameter_schema:{}}]};
 else if(p.endsWith('/research-agent'))body={items:[{id:'audit',name:'Audit fixture',state:'BASELINE_ANALYSIS',baseline_run_id:1}]};
 else if(p.endsWith('/concept-audits')){if(method==='POST'){const row={id:'one',request:JSON.parse(options.body),status:'COMPLETED',report};items.push(row);body=row;}else body={items};}
 return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}});};
}
await send('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixtures.toString()})()`});
await send('Page.navigate',{url:base+'/?concept-audit='+Date.now()});
await waitFor(`document.body.innerText.includes('Market Concepts')`);await click('Market Concepts');
await waitFor(`document.body.innerText.includes('Audit fixture')`);
assert(await evaluate(`!auditCalls.some(c=>c.method==='POST')`));
const choose=async(label,value)=>evaluate(`(()=>{const el=[...document.querySelectorAll('label')].find(l=>l.textContent.startsWith(${JSON.stringify(label)})).querySelector('select');Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(el,${JSON.stringify(value)});el.dispatchEvent(new Event('change',{bubbles:true}));})()`);
await choose('Development project','audit');await choose('Exact concept version','swing.strict.v1');
assert(await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='Run concept audit').disabled`));
await evaluate(`[...document.querySelectorAll('label')].find(l=>l.textContent.includes('Audit verified development data')).querySelector('input').click()`);
await click('Run concept audit');await waitFor(`document.body.innerText.includes('prefix checks PASS')`);
await evaluate(`[...document.querySelectorAll('summary')].find(s=>s.textContent.includes('prefix checks PASS')).click()`);
await click('Inspect Swing high #1');await waitFor(`document.querySelectorAll('canvas').length>0`);
assert(await evaluate(`document.body.innerText.includes('retrospective diagnostics only')`));
assert.equal(await evaluate(`auditCalls.filter(c=>c.method==='POST').length`),1);
for(const width of [1024,1440,1920]){await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`),'Overflow '+width);}
await click('Close concept example');
assert.equal(errors.length,0,errors.join('\n'));
console.log('PASS concept audit explicit consent, request, saved report, confirmation-aware chart, 1024/1440/1920, no runtime errors.');close();
