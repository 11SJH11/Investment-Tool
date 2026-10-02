import test from 'node:test';
import assert from 'node:assert/strict';
import {checkpointKey,writeReplayCheckpoint,replayNeedsGuard} from '../src/features/strategy-lab/replayCheckpoint.js';
const payload={config:{symbol:'NQ1!'},anchorTimestamp:'2026-09-01T14:30:00Z',frontierTimestamp:'2026-09-01T14:35:00Z',position:null,pendingOrder:null,closedTrade:{source_contract:'NQU6',net_pnl:20},contracts:'2',integrityCompromised:true};
test('checkpoint retains canonical frontiers, closed trade and contract facts exactly',()=>{
 const map=new Map(),storage={setItem:(k,v)=>map.set(k,v),getItem:k=>map.get(k)};
 const encoded=writeReplayCheckpoint(storage,payload);assert.deepEqual(JSON.parse(map.get(checkpointKey)),payload);
 assert.equal(replayNeedsGuard(payload,encoded),false);assert.equal(replayNeedsGuard({...payload,contracts:'3'},encoded),true);
});
test('guard covers initial unsaved state and active or pending simulations even after a checkpoint',()=>{
 assert.equal(replayNeedsGuard(null,null),false);assert.equal(replayNeedsGuard(payload,null),true);
 for(const key of ['position','pendingOrder','pendingClose']){const active={...payload,[key]:true};assert.equal(replayNeedsGuard(active,JSON.stringify(active)),true);}
});
test('checkpoint storage failure or failed readback cannot report successful persistence',()=>{
 for(const storage of [{setItem(){throw Error('quota');}},{setItem(){},getItem(){return 'old';}},{setItem(){},getItem(){throw Error('blocked');}}])assert.throws(()=>writeReplayCheckpoint(storage,payload),/Could not save/);
 assert.throws(()=>writeReplayCheckpoint({},null),/frontier/);
});
