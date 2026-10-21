import test from 'node:test';
import assert from 'node:assert/strict';
import {pollCampaign} from '../src/features/strategy-lab/campaignPolling.js';

const flush=()=>new Promise(resolve=>setImmediate(resolve));
function harness(fetchReport){
 const queued=[],reports=[],connections=[];
 const stop=pollCampaign({fetchReport,onReport:r=>reports.push(r),onConnection:c=>connections.push(c),
  schedule:(fn,ms)=>{const item={fn,ms};queued.push(item);return item;},cancel:item=>{if(item)item.cancelled=true;},now:()=>1234});
 return {queued,reports,connections,stop};
}
test('transient failure retains report and retries, then clears stale state',async()=>{
 const sequence=[{campaign:{status:'ACTIVE'}},Error('Offline'),{campaign:{status:'DEVELOPMENT_COMPLETE'}}];
 const r=harness(async()=>{const value=sequence.shift();if(value instanceof Error)throw value;return value;});
 await flush();await r.queued.shift().fn();
 assert.equal(r.reports.length,1);assert.equal(r.connections.at(-1).lastSuccess,1234);
 assert.equal(r.connections.at(-1).error,'Offline');
 await r.queued.shift().fn();
 assert.equal(r.reports.length,2);assert.equal(r.connections.at(-1).error,null);
 assert.equal(r.queued.length,0);r.stop();
});
test('retries are bounded and stopping suppresses pending responses',async()=>{
 const h=harness(async()=>{throw Error('Offline');});await flush();
 const delays=[];for(let i=0;i<7;i++){const task=h.queued.shift();delays.push(task.ms);await task.fn();}
 assert.deepEqual(delays,[2500,5000,10000,20000,30000,30000,30000]);h.stop();
 assert.equal(h.queued[0].cancelled,true);
 let resolve;const pending=harness(()=>new Promise(r=>{resolve=r;}));pending.stop();
 resolve({campaign:{status:'ACTIVE'}});await flush();
 assert.equal(pending.reports.length,0);assert.equal(pending.queued.length,0);
});
test('one request at a time; validation continues after development ends',async()=>{
 let resolve,calls=0;
 const h=harness(()=>{calls++;return new Promise(r=>{resolve=r;});});
 assert.equal(calls,1);assert.equal(h.queued.length,0);
 resolve({campaign:{status:'DEVELOPMENT_COMPLETE',execution:{validation_contract:{}},validation:{status:'ACTIVE'}}});
 await flush();assert.equal(h.queued[0].ms,2500);h.stop();
});
