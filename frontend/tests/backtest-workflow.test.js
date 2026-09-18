import test from 'node:test';
import assert from 'node:assert/strict';
import {RUN_TYPES,parseSymbols,independentRuns,runSummary,filterRuns,queueCounts,configurationError} from '../src/features/strategy-lab/backtest-workflow.js';
import {readUI,writeUI} from '../src/app/uiPreferences.js';

test('run modes retain single, validation and sensitivity workflows',()=>assert.deepEqual(RUN_TYPES,['Single backtest','Validation suite','Sensitivity test']));
test('invalid or zero sizing cannot silently queue engine fallback amounts',()=>{
  const p={symbols:['AAPL'],start_date:'2026-01-01',end_date:'2026-01-02',starting_balance:10000,risk_value:1,max_leverage:1,max_open_positions:1,commission_per_order:0,slippage_bps:0,spread_bps:0,trading_weekdays:[0]};
  assert.equal(configurationError(p),'');assert.match(configurationError({...p,risk_value:0}),/positive/);assert.match(configurationError({...p,starting_balance:NaN}),/positive/);assert.match(configurationError({...p,symbols:[]}),/symbol/);
});
test('paste parses common delimiters, normalises symbols and removes duplicates',()=>assert.deepEqual(parseSymbols('aapl, MSFT\nNVDA;aapl NQ1!'),['AAPL','MSFT','NVDA','NQ1!']));
test('batch snapshots isolate symbols and capital, preserve settings and do not mutate input',()=>{
  const base={symbols:['AAPL','MSFT'],starting_balance:10000,risk_value:1,strategy_params:{x:2},experiment_group:'holdout',run_name:'test'};
  const snapshot=JSON.stringify(base),runs=independentRuns(base);
  assert.equal(runs.length,2);assert.deepEqual(runs.map(r=>r.symbols),[['AAPL'],['MSFT']]);
  assert.ok(runs.every(r=>r.starting_balance===10000&&r.risk_value===1));
  assert.deepEqual(runs.map(r=>r.experiment_group),['holdout-AAPL','holdout-MSFT']);assert.equal(JSON.stringify(base),snapshot);
});
test('ready summary reflects costs, sizing, dates and per-symbol sessions',()=>{
  const p={symbols:['AAPL','NQ1!'],primary_timeframe:'1m',start_date:'2026-01-01',end_date:'2026-01-31',starting_balance:10000,sizing_mode:'cash_risk',risk_value:25,commission_per_order:2,slippage_bps:3,spread_bps:4,session:'auto',test_role:'out_of_sample',same_bar_policy:'stop_first',max_leverage:1};
  const s=runSummary(p);assert.equal(s.Session,'regular / 24h (per instrument)');assert.equal(s.Sizing,'cash risk · 25');assert.match(s.Costs,/2\/order.*3 bps.*4 bps/);assert.equal(s.Role,'out of sample');assert.match(s.Balance,/10,000 per independent run/);
});
const runs=[{id:1,name:'Alpha',symbols:['AAPL'],strategy_name:'VWAP',test_role:'development',trades:5,total_r:-1,created_at:'2026-01-02'},{id:2,name:'Beta',symbols:['MSFT'],strategy_name:'VWAP',test_role:'validation',trades:10,total_r:3,created_at:'2026-02-02'},{id:3,name:'Gamma',symbols:['AAPL'],strategy_name:'ORB',test_role:'out_of_sample',trades:0,total_r:null,created_at:'2026-03-02'}];
test('categorical filters combine checkbox selections without mutating snapshots',()=>{assert.deepEqual(filterRuns(runs,{symbols:['AAPL'],strategy_name:['VWAP','ORB']}).map(r=>r.id),[3,1]);assert.equal(runs[0].id,1);});
test('numeric between and zero bounds exclude missing metrics',()=>{assert.deepEqual(filterRuns(runs,{total_r:{kind:'number',min:'0',max:'3'}}).map(r=>r.id),[2]);assert.deepEqual(filterRuns(runs,{trades:{kind:'number',min:'0',max:'0'}}).map(r=>r.id),[3]);});
test('strict greater and less filters do not include equal boundary values',()=>{
  assert.deepEqual(filterRuns(runs,{trades:{kind:'number',operator:'greater',min:'5'}}).map(r=>r.id),[2]);
  assert.deepEqual(filterRuns(runs,{trades:{kind:'number',operator:'less',max:'5'}}).map(r=>r.id),[3]);
});
test('date range, text search and numeric sorting work together',()=>{assert.deepEqual(filterRuns(runs,{created_at:{kind:'date',min:'2026-01-01',max:'2026-02-28'},name:'a'},{key:'trades',direction:'desc'}).map(r=>r.id),[2,1]);});
test('queue summary counts actual states including preparing and cancellation',()=>assert.deepEqual(queueCounts(['queued','queued','running','completed','failed','cancelled','preparing data'].map(status=>({status}))),{queued:2,running:1,completed:1,failed:1,cancelled:1,'preparing data':1}));
test('presentation preferences persist across reloads and tolerate unavailable storage',()=>{
  const map=new Map(),storage={getItem:k=>map.get(k),setItem:(k,v)=>map.set(k,v)};
  writeUI('runs.filters',{symbols:['AAPL']},storage);assert.deepEqual(readUI('runs.filters',{},storage),{symbols:['AAPL']});
  for(const key of ['backtest.runType','section.costs','runs.columns','runs.sort','backtest.resultView']){writeUI(key,'saved',storage);assert.equal(readUI(key,null,storage),'saved');}
  assert.equal(readUI('bad','fallback',{getItem:()=>'{broken'}),'fallback');assert.doesNotThrow(()=>writeUI('x',1,{setItem:()=>{throw Error('full');}}));
});
