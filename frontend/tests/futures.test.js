import test from 'node:test';
import assert from 'node:assert/strict';
import {replayEconomics} from '../src/features/strategy-lab/futures-utils.js';

const nq = {asset_type:'future',execution_supported:true,tick_size:.25,contract_multiplier:20};
test('Replay uses whole futures contracts and dollar multiplier', () => {
  const p=replayEconomics(nq,1,25000,[24990,25020]);
  assert.equal(p.quantity,1);
  assert.equal((25020-25000)*p.quantity*p.contract_multiplier,400);
  assert.throws(()=>replayEconomics(nq,.5,25000),/whole/);
  assert.throws(()=>replayEconomics(nq,1,25000,[24990.1]),/tick/);
});
test('continuous aliases and missing economics cannot create Replay positions', () => {
  assert.throws(()=>replayEconomics({...nq,execution_supported:false},1,25000),/chart-only/);
  assert.throws(()=>replayEconomics({...nq,tick_size:null},1,25000),/Verified/);
});
test('equity and spot Replay sizing is unchanged', () => {
  assert.deepEqual(replayEconomics({asset_type:'equity'},1000,100),{quantity:10,contract_multiplier:1});
});
