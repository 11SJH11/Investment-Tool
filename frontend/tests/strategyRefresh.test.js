import test from 'node:test';
import assert from 'node:assert/strict';
import {refreshedSelection,normalBacktestTab} from '../src/features/strategy-lab/strategyRefresh.js';
test('Refresh uses new backend list, updates defaults and preserves explicit inputs',()=>{
 const before=[{key:'a',defaults:{x:1,y:2,removed:3}}];
 const response={ok:true,added:1,updated:1,removed:0,strategies:[{key:'a',defaults:{x:4,y:8,z:9}},{key:'new',defaults:{}}]};
 const next=refreshedSelection(before,response,'a',{x:1,y:7,removed:3});
 assert.equal(next.key,'a');assert.deepEqual(next.params,{x:4,y:7,z:9});
 assert.equal(next.strategies.length,2);assert.match(next.message,/1 added/);
});
test('Refresh failures surface module errors without replacing existing state',()=>{
 const before=[{key:'a',defaults:{x:1}}];
 assert.throws(()=>refreshedSelection(before,{ok:false,errors:[{module:'bad.py',message:'SyntaxError'}]},'a',{}),/bad.py: SyntaxError/);
 assert.deepEqual(before,[{key:'a',defaults:{x:1}}]);
});
test('Removed selection falls back safely and saved Workspace navigation is hidden',()=>{
 assert.equal(refreshedSelection([],{ok:true,strategies:[{key:'new'}]},'old',{}).key,'new');
 assert.equal(normalBacktestTab('Workspace'),'Backtest');
 assert.equal(normalBacktestTab('Strategies'),'Strategies');
});
