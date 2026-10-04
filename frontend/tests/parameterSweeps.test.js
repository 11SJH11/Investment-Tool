import test from 'node:test';
import assert from 'node:assert/strict';
import {sweepAxes} from '../src/features/strategy-lab/parameterSweeps.js';
import {requestLabel,beginRequest,subscribeBusy} from '../src/app/activityEvents.js';
test('integrated sweeps preserve exact decimal input for canonical backend validation',()=>{
 assert.deepEqual(sweepAxes({fixed:{mode:'fixed',values:'1'},x:{mode:'range',start:'1.0',end:'2.0',step:'.25'},y:{mode:'explicit',values:'1,2'}}),[{parameter:'x',mode:'range',start:'1.0',end:'2.0',step:'.25'},{parameter:'y',mode:'explicit',values:'1,2'}]);
});
test('busy tracking survives overlapping requests and excludes silent job polls',()=>{
 const states=[];const unsubscribe=subscribeBusy(s=>states.push(s));const a=beginRequest('Run'),b=beginRequest('Chart');a();b();unsubscribe();
 assert.deepEqual(states,[[],['Run'],['Run','Chart'],['Chart'],[]]);
 assert.equal(requestLabel('/strategy-lab/jobs?compact=true'),null);assert.equal(requestLabel('/brokers/private-id/sync','POST'),'Synchronising broker');
 assert.equal(requestLabel('/strategy-lab/runs/1/sections/summary'),'Loading saved run');
});
