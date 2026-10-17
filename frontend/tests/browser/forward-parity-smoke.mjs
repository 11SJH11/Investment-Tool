import {send,evaluate,waitFor,errors,close} from './cdp.mjs';
await send('Page.navigate',{url:process.env.LEDGER_SMOKE_URL||'http://127.0.0.1:19383'});
await waitFor(`document.querySelector('#root')`);
await evaluate(`(async()=>{
 const {default:React}=await import('/node_modules/.vite/deps/react.js');
 const {default:ReactDOM}=await import('/node_modules/.vite/deps/react-dom_client.js');
 const {default:Panel}=await import('/src/features/strategy-lab/ForwardParity.jsx');
 const container=document.createElement('div');container.id='parity-test';container.style='position:fixed;inset:0;overflow:auto;background:white;z-index:999999';document.body.append(container);
 const root=ReactDOM.createRoot(container);window.parityRequests=[];
 window.fetch=async(url,options={})=>{window.parityRequests.push({url:String(url),body:JSON.parse(options.body||'{}')});return new Response('{}',{headers:{'Content-Type':'application/json'}});};
 function render(reports=[]){root.render(React.createElement(Panel,{experiment:'fixture',reports,onChecked:async()=>render([{session_date:'2026-01-02',checked_at:'fixture',status:'FAIL',results:[{deployment_id:'B',name:'B shadow',status:'FAIL',checks:{setup_sha256:false,trade_sha256:true}}]}])}));}
 render();
})()`);
await waitFor(`document.querySelector('#parity-test summary')`);
await evaluate(`document.querySelector('#parity-test summary').click()`);
if(!await evaluate(`document.querySelector('#parity-test button').disabled`))throw Error('Missing date gate');
await evaluate(`(()=>{const el=document.querySelector('#parity-test input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'2026-01-02');el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));})()`);
await waitFor(`!document.querySelector('#parity-test button').disabled`);
await evaluate(`document.querySelector('#parity-test button').click()`);
await waitFor(`document.querySelector('#parity-test').textContent.includes('differing checks: setup_sha256')`);
if(await evaluate(`window.parityRequests[0].body.session_date!=='2026-01-02'||!window.parityRequests[0].url.endsWith('/forward/fixture/parity')`))throw Error('Parity request contract');
for(const width of [1024,1440,1920]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
 if(await evaluate(`document.querySelector('#parity-test').scrollWidth>innerWidth`))throw Error('Page overflow');
 console.log('Session parity '+width+': passed');
}
if(errors.length)throw Error(errors.join('\n'));close();
