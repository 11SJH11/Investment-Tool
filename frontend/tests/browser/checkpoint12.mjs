// Isolated local fixture only. No production data or provider credentials.
import assert from 'node:assert/strict';
const base=process.env.LEDGER_SMOKE_URL;
assert(base&&['127.0.0.1','localhost'].includes(new URL(base).hostname));
const {send,evaluate,click,fill,waitFor,screenshot,errors,close}=await import('./cdp.mjs');
const pause=ms=>new Promise(r=>setTimeout(r,ms||450));
const nav=text=>evaluate(`[...document.querySelectorAll('[aria-label="Main navigation"] button')].find(b=>b.textContent===${JSON.stringify(text)}).click()`);
const input=(selector,value)=>evaluate(`(()=>{const i=document.querySelector(${JSON.stringify(selector)});if(!i)throw Error('Missing input '+${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(i.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set.call(i,${JSON.stringify(value)});i.dispatchEvent(new Event(i.tagName==='SELECT'?'change':'input',{bubbles:true}));})()`);
await send('Page.addScriptToEvaluateOnNewDocument',{source:`{const original=window.fetch;window.__requests=[];window.fetch=(url,...args)=>{url=String(url).replace('http://localhost:8000/api','/api').replace('http://127.0.0.1:8000/api','/api');window.__requests.push(url);return original(url,...args)};window.confirm=()=>true;const raf=window.requestAnimationFrame;window.__frames=0;window.requestAnimationFrame=cb=>raf.call(window,t=>{window.__frames++;cb(t)});}`});
await send('Network.enable');await send('Network.setCacheDisabled',{cacheDisabled:true});
const url=base+'/?smoke='+Date.now();await send('Page.navigate',{url});await waitFor(`location.href===${JSON.stringify(url)}&&document.querySelector('[aria-label="Main navigation"]')`);errors.length=0;
await nav('Research');await waitFor(`document.querySelectorAll('[aria-label="Screener results"] tbody tr').length===4`);
assert(await evaluate(`document.body.innerText.includes('Technical coverage 4/4')`));
await click('Reset scan');await pause();await click('+ Add condition');await input('[aria-label="Condition 1 field"]','ema20');await input('[aria-label="Condition 1 comparison"]','ema50');await click('Run screener');await waitFor(`!document.body.innerText.includes('Scanning...')`);assert.equal(await evaluate(`document.querySelectorAll('[aria-label="Screener results"] tbody tr').length`),4);
await input('[aria-label="Scan name"]','CP12 trend');await click('Save');await click('Duplicate');assert(await evaluate(`document.querySelector('[aria-label="Saved scan"] option:last-child').textContent==='CP12 trend copy'`));await click('Delete scan');
await evaluate(`document.querySelector('[aria-label="Screener results"] tbody button').click()`);await waitFor(`document.querySelector('.market-chart-panel canvas')`);await pause();assert.equal(await evaluate(`document.querySelector('.chart-timeframe-badge').textContent`),'1d');
await evaluate(`[...document.querySelectorAll('.chart-global-toolbar button')].find(b=>b.textContent==='5m').click()`);await pause(900);await waitFor(`!document.querySelector('.chart-loading,.chart-error')`);
await pause(500);const idleBefore=await evaluate('window.__frames');await pause(1000);const idleFrames=await evaluate(`window.__frames-${idleBefore}`);assert(idleFrames<5,'Idle RAF callbacks '+idleFrames);console.log('PERF idle RAF callbacks / 1s:',idleFrames);
await evaluate(`[...document.querySelectorAll('.chart-settings summary')][0].click()`);await input('[aria-label="Chart template name"]','CP12 clean');await click('Save template');await click('Apply template');await pause();await evaluate(`[...document.querySelectorAll('.chart-settings summary')][0].click()`);
await evaluate(`[...document.querySelectorAll('.chart-actions summary')][0].click()`);await click('Replay from here');await waitFor(`document.body.innerText.includes('Historical Replay')`);console.log('PASS Screener field comparison, saved scan CRUD, Chart template, Chart -> Replay');
await fill('Replay starts','2026-09-01');await fill('Replay through','2026-09-02');await evaluate(`(()=>{const i=[...document.querySelectorAll('label')].find(l=>l.textContent.includes('Start time')).querySelector('input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(i,'09:30');i.dispatchEvent(new Event('input',{bubbles:true}));})()`);
await click('Load replay');await waitFor(`document.querySelector('.replay-toolbar')`);await pause(400);
await click('BUY / LONG');await click('Next bar');await waitFor(`document.body.innerText.includes('Close manually on next bar open')`);await click('Close manually on next bar open');await click('Next bar');await waitFor(`document.body.innerText.includes('Journal as replay trade #')`);
assert(await evaluate(`Boolean(document.querySelector('[aria-label="Replay timeframe"]'))`),'Replay timeframe controls should be visible outside full screen');
assert.equal(await evaluate(`[...document.querySelectorAll('.replay-toolbar button')].some(b=>b.textContent.trim()==='Current')`),false,'Removed Current control must not return');
const beforeFive=await evaluate(`document.querySelector('.replay-toolbar-title').textContent`);await click('+5 bars');await pause(700);const afterFive=await evaluate(`document.querySelector('.replay-toolbar-title').textContent`);assert.notEqual(afterFive,beforeFive,'+5 timeframe bars should advance the replay title');await click('Previous');await pause(500);const afterPrevious=await evaluate(`document.querySelector('.replay-toolbar-title').textContent`);assert.notEqual(afterPrevious,afterFive,'Previous should review one selected-timeframe candle');assert(await evaluate(`[...document.querySelectorAll('button')].some(b=>b.textContent==='Load replay'&&!b.disabled)`));
await input('[aria-label="Replay jump UTC"]','2026-09-01T14:00');await waitFor(`[...document.querySelectorAll('button')].some(b=>b.textContent==='Jump'&&!b.disabled)`);await click('Jump');await waitFor(`document.querySelector('.replay-toolbar').innerText.includes('10:00')`);
await evaluate(`(()=>{const i=[...document.querySelectorAll('label')].find(l=>l.textContent.includes('Display timezone')).querySelector('select');i.value='Europe/London';i.dispatchEvent(new Event('change',{bubbles:true}));})()`);await pause();
console.log('PASS Replay market fill, next-open close, automatic Journal, step/rewind/jump');
const layouts=[];
for(const width of [1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
 for(const label of ['Overview','Charts','Replay','Backtest','Journal','Portfolio','Research','Settings']){
  await nav(label);await pause(550);
  const layout=await evaluate(`({viewport:innerWidth,body:document.documentElement.scrollWidth,main:document.querySelector('main').scrollWidth,client:document.querySelector('main').clientWidth})`);
  layouts.push({width,page:label,...layout});assert(layout.body<=width+1&&layout.main<=layout.client+1,JSON.stringify(layouts.at(-1)));
  if(['Charts','Replay','Research'].includes(label))await screenshot(`cp12-${label}-${width}.png`);
 }
}
assert.equal(errors.length,0,errors.join('\n'));console.log('PASS viewport checks',JSON.stringify(layouts));close();
