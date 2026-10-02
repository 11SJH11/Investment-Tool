import test from 'node:test';
import assert from 'node:assert/strict';
import {createStatusPoller,activeStatus,researchCount} from '../src/features/strategy-lab/statusPolling.js';
import {experimentCells} from '../src/features/strategy-lab/researchExperiments.js';
function clock(){const timers=new Map();let id=0;return {timers,setTimeout(fn){timers.set(++id,fn);return id},clearTimeout(id){timers.delete(id)}}}
test('shared subscribers coalesce requests and stop polling on terminal state',async()=>{
 const c=clock();let calls=0,active=true;const received=[];
 const resource=createStatusPoller(async()=>{calls++;return {active}},d=>d.active,10,c);
 const a=resource.subscribe(d=>received.push(d)),b=resource.subscribe(()=>{});
 await Promise.all([resource.refresh(),resource.refresh()]);assert.equal(calls,1);assert.equal(c.timers.size,1);
 active=false;await resource.refresh();assert.equal(calls,2);assert.equal(c.timers.size,0);
 a();b();assert.equal(c.timers.size,0);assert.equal(received.at(-1).active,false);
});
test('unmount clears timer and an in-flight completion cannot restart it',async()=>{
 const c=clock();let resolve;const resource=createStatusPoller(()=>new Promise(r=>resolve=r),()=>true,10,c);
 const unsubscribe=resource.subscribe(()=>{});const pending=resource.refresh();await Promise.resolve();unsubscribe();resolve({active:true});await pending;
 assert.equal(c.timers.size,0);
});
test('explicit refresh recovers errors and restarts active polling',async()=>{
 const c=clock();let fail=true,errors=0;const resource=createStatusPoller(async()=>{if(fail)throw Error('offline');return {active:true}},d=>d.active,10,c);
 const unsubscribe=resource.subscribe((d,e)=>{if(e)errors++});await resource.refresh();assert.equal(errors,1);assert.equal(c.timers.size,0);
 fail=false;await resource.refresh();assert.equal(c.timers.size,1);unsubscribe();assert.equal(c.timers.size,0);
});
test('compact cells retain all metrics without trade or configuration payloads',()=>{
 const metrics={trades:12,expectancy_r:.4,average_mfe:1.5,average_mae:.2,mfe_n:10,mae_n:11,stop_pct:25,target_pct:50};
 const plan={axes:[{default:1,values:[1]}],cells:[[1]]};
 const [cell]=experimentCells(plan,[],[],[{index:0,status:'completed',run_id:7,metrics}]);
 assert.deepEqual(cell.metrics,metrics);assert.equal(cell.runId,7);assert.equal(cell.lowN,true);assert.equal(cell.control,true);
 assert.equal(researchCount({payload:{research_count:25}}),25);assert.equal(researchCount({payload:{research_children:[{},{}]}}),2);
 assert(activeStatus('preparing shared data'));assert(!activeStatus('failed'));
});

test('old server 404 uses the full research endpoint; real failures stay visible',async()=>{
 const {fetchResearchUpdate}=await import('../src/features/strategy-lab/statusPolling.js');let full=0;
 const api={researchExperimentStatus:async()=>{throw Object.assign(Error('missing'),{status:404});},strategyLabExperiment:async()=>{full++;return {runs:[{id:1}]};}};
 assert.deepEqual(await fetchResearchUpdate(api,'g'),{detail:{runs:[{id:1}]}});assert.equal(full,1);
 api.researchExperimentStatus=async()=>({status:'running'});assert.deepEqual(await fetchResearchUpdate(api,'g'),{status:{status:'running'}});assert.equal(full,1);
 api.researchExperimentStatus=async()=>{throw Object.assign(Error('unavailable'),{status:503});};await assert.rejects(()=>fetchResearchUpdate(api,'g'),/unavailable/);assert.equal(full,1);
});
