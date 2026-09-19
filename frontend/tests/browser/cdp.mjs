import fs from 'node:fs';
const targets=await (await fetch((process.env.LEDGER_CDP_URL||'http://127.0.0.1:19240')+'/json')).json();
const target=targets.find(t=>t.type==='page');
const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
let next=0;const pending=new Map();export const errors=[];
ws.onmessage=e=>{const msg=JSON.parse(e.data);if(msg.id){const p=pending.get(msg.id);pending.delete(msg.id);msg.error?p.reject(msg.error):p.resolve(msg.result);}else if(msg.method==='Runtime.exceptionThrown')errors.push(msg.params.exceptionDetails.text+': '+msg.params.exceptionDetails.exception?.description);};
export function send(method,params={}){return new Promise((resolve,reject)=>{const id=++next;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});}
export async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value;}
export async function waitFor(expression){for(let i=0;i<200;i++){if(await evaluate(`Boolean(${expression})`))return;await new Promise(r=>setTimeout(r,100));}throw new Error('Timed out: '+expression);}
export const click=text=>evaluate(`(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()===${JSON.stringify(text)});if(!b)throw Error('Button missing: '+${JSON.stringify(text)});b.click();})()`);
export const fill=(label,value)=>evaluate(`(()=>{const label=[...document.querySelectorAll('label')].find(l=>l.querySelector('span')?.textContent.trim()===${JSON.stringify(label)});const el=label?.querySelector('input,textarea');if(!el)throw Error('Input missing: '+${JSON.stringify(label)});Object.getOwnPropertyDescriptor(el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(el,${JSON.stringify(value)});el.dispatchEvent(new Event('input',{bubbles:true}));})()`);
export async function screenshot(name){const r=await send('Page.captureScreenshot',{format:'png'});if(process.env.LEDGER_SMOKE_OUTPUT)fs.writeFileSync(process.env.LEDGER_SMOKE_OUTPUT+'/'+name,Buffer.from(r.data,'base64'));}
export function close(){ws.close();}
await send('Runtime.enable');await send('Page.enable');
