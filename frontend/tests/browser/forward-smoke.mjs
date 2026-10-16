import {send,evaluate,waitFor,click,errors,close} from './cdp.mjs';
errors.length=0;
await send('Page.addScriptToEvaluateOnNewDocument',{source:`
localStorage.setItem('ledger.ui.navigation.active',JSON.stringify('Backtest'));
localStorage.setItem('ledger.ui.backtest.tab',JSON.stringify('Forward Validation'));
window.preparations=[];window.stops=[];let items=[];
window.fetch=async(url,opts={})=>{const path=new URL(String(url),location.origin).pathname;let data={items:[]};
if(path.endsWith('/strategies'))data={strategies:[]};
if(path.endsWith('/indicators'))data={indicators:[]};
if(path.endsWith('/runs'))data={runs:[]};
if(path.endsWith('/jobs'))data={jobs:[],max_workers:1,compute:{}};
if(path.endsWith('/forward/prepare')){window.preparations.push(JSON.parse(opts.body));items=[{id:'experiment',preparation:{status:'READY'},deployments:['BASELINE','B','C','D'].map(name=>({id:name,name:'VWAP_'+name+'_SHADOW_V1',definition:{feed:'iex'},state:{status:'ACTIVE',equity:10000,trade_count:0,trades_today:0,trade_history:[],position:null}}))}];}
if(path.endsWith('/forward/experiment/halt')){window.stops.push(path);items[0].preparation.status='STOPPED';items[0].deployments.forEach(d=>d.state.status='HALTED');}
if(path.includes('/forward'))data={configured:true,provider:'alpaca',feed:'iex',items};
return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
};`});
await send('Page.navigate',{url:process.env.LEDGER_SMOKE_URL||'http://127.0.0.1:19383'});
await waitFor(`document.querySelector('[aria-label="Forward validation"]')`);
await evaluate(`([...document.querySelectorAll('summary')].find(s=>s.textContent==='Start an IEX shadow experiment')).click()`);
await waitFor(`document.body.textContent.includes('IEX covers one exchange')`);
if(!await evaluate(`([...document.querySelectorAll('button')].find(b=>b.textContent==='Prepare and start shadows')).disabled`))throw Error('Consent missing');
await evaluate(`document.querySelector('[aria-label="Forward validation"] input[type=checkbox]').click()`);
await click('Prepare and start shadows');
await waitFor(`document.body.textContent.includes('VWAP_D_SHADOW_V1')`);
if(await evaluate(`window.preparations.length!==1||window.preparations[0].account.starting_balance!==10000`))throw Error('Preparation contract');
await click('Stop shadows');
await waitFor(`document.body.textContent.includes('STOPPED')`);
if(await evaluate(`window.stops.length!==1`))throw Error('Stop contract');
for(const width of [1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
 if(await evaluate(`document.documentElement.scrollWidth>innerWidth+1`))throw Error('Overflow at '+width);
 console.log('Forward validation '+width+': passed');
}
if(errors.length)throw Error(errors.join('\n'));
console.log('Consent, preparation, four states, stop and runtime checks passed');close();
