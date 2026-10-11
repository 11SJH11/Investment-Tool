import test from 'node:test';
import assert from 'node:assert/strict';
import {campaignActions,campaignIsRunning,campaignPayload,LAUNCH_CONSENT} from '../src/features/strategy-lab/campaignView.js';
const form={mode:'FIND_STRATEGIES',strategy_key:'ignored',symbols:'qqq QQQ, spy',timeframe:'1m',prompt:'',history:'cached',
 model:false,structural:true,numeric_cycles:2,starting_balance:10000,risk_value:1,commission_per_order:0,spread_bps:1,slippage_bps:2,max_leverage:1};
const policy={budget:{llm_usd:10},holdout:'human_approval',external_research:true};
test('Campaign launch preserves explicit costs, disables unconsented model/code and has no user-selected dates',()=>{
 const result=campaignPayload(form,policy,'identity');
 assert.deepEqual(result.campaign.policy.symbols,['QQQ','SPY']);
 assert.equal(result.campaign.strategy_key,null);
 assert.equal(result.numeric_cycles,0);assert.equal(result.structural,false);
 assert.equal(result.engine.sizing_mode,'risk_pct');assert.equal(result.engine.spread_bps,1);
 assert.equal(result.engine.start_date,undefined);assert.equal(result.engine.strategy_key,undefined);
 assert.equal(result.campaign.policy.external_research,false);assert.equal(result.consent,LAUNCH_CONSENT);
 assert.equal(policy.external_research,true);
});
test('Improve strategy retains identity and explicit model/child permission',()=>{
 const result=campaignPayload({...form,mode:'IMPROVE_STRATEGY',strategy_key:'vwap',model:true},policy,'key');
 assert.equal(result.campaign.strategy_key,'vwap');assert.equal(result.structural,true);
 assert.equal(result.numeric_cycles,2);assert.equal(result.campaign.policy.holdout,'human_approval');
 assert.equal(result.campaign.request_key,'key');
});
test('Invalid settings cannot silently become a zero-cost or empty research request',()=>{
 for(const changes of [{symbols:''},{risk_value:''},{starting_balance:0},{max_leverage:NaN},{slippage_bps:-1},{mode:'IMPROVE_STRATEGY',strategy_key:''}]){
  assert.throws(()=>campaignPayload({...form,...changes},policy,'id'));
 }
});
test('Campaign controls reflect backend lifecycle; terminal reports do not poll or restart',()=>{
 assert.deepEqual(campaignActions('ACTIVE'),['pause','stop_after_current','cancel']);
 assert.deepEqual(campaignActions('PAUSED'),['resume','cancel']);
 for(const status of ['DEVELOPMENT_COMPLETE','BASELINES_COMPLETE','CANCELLED','PREPARATION_FAILED','BUDGET_EXHAUSTED']){
  assert.equal(campaignIsRunning(status),false);assert.deepEqual(campaignActions(status),[]);
 }
 assert.equal(campaignIsRunning('PREPARING'),true);
});
