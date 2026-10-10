import test from 'node:test';
import assert from 'node:assert/strict';
import {brokerDate, percent, positionMetrics, returnPercent} from '../src/features/portfolio/brokerPortfolioUtils.js';

test('position prices and wallet metrics retain independent currencies and provider facts',()=>{
  const facts={instrument:{ticker:'VWRP_UK_EQ',name:'Vanguard FTSE All-World',currency:'USD'},quantity:39.0479,
    averagePricePaid:100,currentPrice:110,walletImpact:{currency:'GBP',totalCost:3000,currentValue:3200,unrealizedProfitLoss:200}};
  const p=positionMetrics(facts);
  assert.equal(p.name,'Vanguard FTSE All-World');assert.equal(p.ticker,'VWRP');assert.equal(p.quantity,39.0479);
  assert.equal(p.priceCurrency,'USD');assert.equal(p.walletCurrency,'GBP');assert.equal(p.averageCost,100);
  assert.equal(p.invested,3000);assert.equal(p.value,3200);assert.equal(p.pnl,200);
  assert.equal(percent(p.returnPct),'+6.67%');assert.equal(facts.instrument.ticker,'VWRP_UK_EQ');
});
test('missing facts never become zero, inferred cost, FX conversion or total return',()=>{
  const p=positionMetrics({instrument:{ticker:'UNKNOWN'},quantity:10,currentPrice:20});
  assert.equal(p.averageCost,undefined);assert.equal(p.invested,undefined);assert.equal(p.value,undefined);
  assert.equal(p.returnPct,null);assert.equal(p.walletCurrency,undefined);
  for(const [pnl,cost] of [[null,10],[10,null],[10,0],[10,-1],[Infinity,10],['10',100]]) assert.equal(returnPercent(pnl,cost),null);
  assert.equal(percent(returnPercent(0,100)),'0.00%');assert.equal(percent(returnPercent(-10,100)),'-10.00%');
  assert.equal(positionMetrics({walletImpact:{totalCost:10,unrealizedProfitLoss:5}}).returnPct,null);
});
test('broker dates use the selected timezone and omit raw seconds',()=>{
  assert.equal(brokerDate('2026-09-17T17:38:44.220+03:00','Europe/London'),'17 Sept 2026, 15:38');
  assert.equal(brokerDate('2026-09-17T17:38:44.220+03:00','UTC'),'17 Sept 2026, 14:38');
  assert.equal(brokerDate(null),'Unavailable');assert.equal(brokerDate('invalid'),'Unavailable');
});

import {activitySemantics} from '../src/features/portfolio/brokerPortfolioUtils.js';
test('activity labels use explicit broker side and supported cash types, never ambiguous signs',()=>{
  assert.equal(activitySemantics({order:{side:'BUY'},fill:{quantity:2}},'orders').direction,'BUY');
  assert.equal(activitySemantics({order:{side:'SELL'},fill:{quantity:-2}},'orders').direction,'SELL');
  assert.equal(activitySemantics({fill:{quantity:-2}},'orders').direction,'Unavailable');
  for(const [type,direction] of [['DEPOSIT','IN'],['WITHDRAWAL','OUT'],['FEE','OUT'],['INTEREST','IN']])assert.equal(activitySemantics({type},'transactions').direction,direction);
  assert.equal(activitySemantics({type:'TRANSFER',amount:-5},'transactions').direction,'Unavailable');
  assert.equal(activitySemantics({type:'TRANSFER',direction:'OUT'},'transactions').direction,'OUT');
});

import {accountsForBroker,brokerAccountTotals} from '../src/features/portfolio/brokerPortfolioUtils.js';
test('broker totals use authoritative account values once and never mix currencies',()=>{
  const a={provider:'trading212',account_key:'a',summary:{currency:'USD',totalValue:120,cash:{availableToTrade:20},investments:{currentValue:100}}};
  const b={provider:'robinhood',account_key:'b',summary:{currency:'USD',totalValue:230}};
  const c={provider:'robinhood',account_key:'c',summary:{currency:'GBP',totalValue:50}};
  assert.deepEqual(brokerAccountTotals([a,b,c,a]),[{currency:'USD',accounts:2,value:350,complete:true},{currency:'GBP',accounts:1,value:50,complete:true}]);
  assert.deepEqual(accountsForBroker([a,b,c],'trading212'),[a]);
  assert.equal(brokerAccountTotals([a,b],'robinhood')[0].value,230);
  assert.equal(brokerAccountTotals([a,{provider:'robinhood',account_key:'d',summary:{currency:'USD'}}])[0].value,null);
});
