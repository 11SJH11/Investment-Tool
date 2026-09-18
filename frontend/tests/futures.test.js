import test from 'node:test';
import assert from 'node:assert/strict';
import {replayEconomics,replaySource,replayRollAction} from '../src/features/strategy-lab/futures-utils.js';

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

const alias={...nq,ticker:'NQ1!',root:'NQ',security_type:'continuous_future'};
const raw={source_contract:'NQU6',continuous_alias:'NQ1!',provider:'massive',roll_schedule_version:'prior-session-volume45-v1',adjustment_mode:'raw',adjustment_method:'none',price_adjustment:0};
test('continuous Replay resolves a revealed raw dated contract with whole-contract economics',()=>{
  assert.equal(replaySource(alias,raw),'NQU6');
  assert.equal(replayEconomics(alias,1,25000,[24990,25020],raw).contract_multiplier,20);
  for(const patch of [{source_contract:'ESU6'},{source_contract:'NQ1!'},{provider:null},{continuous_alias:null},{roll_schedule_version:'unknown'},{adjustment_mode:'back_adjusted'},{price_adjustment:1}]) {
    assert.throws(()=>replayEconomics(alias,1,25000,[],{...raw,...patch}));
  }
  assert.throws(()=>replayEconomics(alias,1,25000));
});
test('cross-roll positions terminate before a fill and old pending orders cancel',()=>{
  assert.throws(()=>replayRollAction(alias,raw,{source_contract:'NQM6'},null),/terminated.*crosses/);
  assert.equal(replayRollAction(alias,raw,null,{source_contract:'NQM6'}),'cancel_order');
  assert.equal(replayRollAction(alias,raw,{source_contract:'NQU6'},null),null);
  assert.equal(replayRollAction(alias,raw,null,null),null);
});
