import test from 'node:test';
import assert from 'node:assert/strict';
import {sandboxApproval,sandboxActive,SANDBOX_ACK} from '../src/features/strategy-lab/researchSandbox.js';
test('sandbox approval preserves explicit control/candidate parameters and consent',()=>{
 const p=sandboxApproval('{"enabled":false}','{"enabled":true}');assert.deepEqual(p.control_parameters,{enabled:false});assert.deepEqual(p.candidate_parameters,{enabled:true});assert.equal(p.acknowledgement,SANDBOX_ACK);assert.equal(p.timeout_seconds,120);
});
test('sandbox rejects malformed/nested parameters and invalid time limits',()=>{
 for(const v of ['[]','null','{"job":{}}','{"x":null}','invalid'])assert.throws(()=>sandboxApproval(v,'{}'));
 for(const seconds of [0,601,10.5])assert.throws(()=>sandboxApproval('{}','{}',seconds));
});
test('only running or queued sandbox attempts expose cancellation',()=>{
 for(const status of ['QUEUED','RUNNING'])assert.equal(sandboxActive({status}),true);
 for(const status of ['COMPLETED','FAILED','CANCELLED','INTERRUPTED'])assert.equal(sandboxActive({status}),false);
});
