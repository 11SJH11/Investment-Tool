import test from 'node:test';
import assert from 'node:assert/strict';
import {compositeBreakdown,sortBreakdown,summariseTrades} from '../src/features/journal/analysisBreakdown.js';

const trades=[
  {id:1,status:'closed',result:'win',r_multiple:2,pnl_amount:200,account_currency:'USD',playbook_title:'Gold Type 3',setup:'Liquidity sweep + Type 3',session_time:'London',opened_at:'2026-09-01T08:35:00Z',review_data:{emotions:['Calm'],mistakes:[],confluences:['FVG','HTF trend']}},
  {id:2,status:'closed',result:'loss',r_multiple:-1,pnl_amount:-100,account_currency:'USD',playbook_title:'Gold Type 3',setup:'Liquidity sweep + Type 3',session_time:'London',opened_at:'2026-09-01T08:42:00Z',review_data:{emotions:['Anxious'],mistakes:['Early entry'],confluences:['FVG']}},
  {id:3,status:'closed',result:'win',r_multiple:1,pnl_amount:80,account_currency:'GBP',playbook_title:'ORB',setup:'Opening range breakout',session_time:'New York',opened_at:'2026-09-01T14:05:00Z',review_data:{emotions:['Calm','Confident'],mistakes:[],confluences:['Volume expansion']}},
];

test('multi-factor Journal breakdown combines dimensions without mutating source trades',()=>{
  const snapshot=structuredClone(trades);
  const rows=compositeBreakdown(trades,['playbook','session','entry_10min','emotion'],'Europe/London');
  assert.ok(rows.some(r=>r.values.playbook==='Gold Type 3'&&r.values.session==='London'&&r.values.emotion==='Calm'));
  assert.ok(rows.some(r=>r.values.playbook==='ORB'&&r.values.emotion==='Confident'));
  assert.deepEqual(trades,snapshot);
});

test('multi-choice dimensions deliberately place one trade in multiple descriptive combinations',()=>{
  const rows=compositeBreakdown([trades[2]],['emotion','confluence'],'UTC');
  assert.equal(rows.length,2);
  assert.deepEqual(new Set(rows.map(r=>r.values.emotion)),new Set(['Calm','Confident']));
  assert.ok(rows.every(r=>r.trades===1));
});

test('Journal breakdown sorting supports sample, best and worst expectancy',()=>{
  const rows=compositeBreakdown(trades,['playbook'],'UTC');
  assert.equal(sortBreakdown(rows,'best')[0].values.playbook,'ORB');
  assert.equal(sortBreakdown(rows,'worst')[0].values.playbook,'Gold Type 3');
  assert.equal(sortBreakdown(rows,'sample')[0].values.playbook,'Gold Type 3');
});

test('Journal summary keeps currencies separate and excludes open trades from realised metrics',()=>{
  const result=summariseTrades([...trades,{id:4,status:'open',result:'win',r_multiple:99,pnl_amount:999,account_currency:'USD'}]);
  assert.equal(result.r_trades,3);
  assert.equal(result.total_r,2);
  assert.deepEqual(result.pnl_by_currency,[{currency:'GBP',total_pnl:80},{currency:'USD',total_pnl:100}]);
});
