import test from 'node:test';
import assert from 'node:assert/strict';
import {jobTransitions,jobDestination} from '../src/app/activityEvents.js';
test('activity only announces observed terminal transitions, never historical jobs on mount',()=>{
 const jobs=[{id:1,status:'completed',run_id:3},{id:2,status:'running'}];
 assert.deepEqual(jobTransitions(new Map(),jobs),[]);
 assert.deepEqual(jobTransitions(new Map([[1,'running'],[2,'queued']]),jobs),[jobs[0]]);
 assert.equal(jobDestination(jobs[1]),null);assert.deepEqual(jobDestination(jobs[0]),{runId:3});
 assert.equal(jobDestination({status:'running',payload:{experiment_group:'x'}}),null);
 assert.deepEqual(jobDestination({status:'completed',payload:{experiment_group:'x'}}),{experimentGroup:'x'});
});
