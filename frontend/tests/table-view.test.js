import test from 'node:test';
import assert from 'node:assert/strict';
import {blankView,normalizeView,tableRows,matches} from '../src/components/table/tableModel.js';
import {weeklySummary,calendarTone} from '../src/features/journal/calendarModel.js';
const columns=[{key:'name',kind:'text'},{key:'type',kind:'category'},{key:'r',kind:'number'},{key:'date',kind:'date',hidden:true}];
const rows=[{id:1,name:'Alpha',type:'BUY',r:2,date:'2026-09-01'},{id:2,name:'Beta',type:'SELL',r:-1,date:'2026-09-02'},{id:3,name:'Gamma',type:'BUY',r:0,date:'2026-09-03'},{id:4,name:'Delta',type:'BUY',r:null,date:null}];
test('universal table category OR and cross-column AND with strict numeric bounds',()=>{
  const view={...blankView(columns),filters:{type:['BUY'],r:{kind:'number',operator:'greater',min:0}}};assert.deepEqual(tableRows(rows,columns,view).map(r=>r.id),[1]);
  assert.equal(matches(null,{kind:'number',min:0}),false);assert.equal(matches(0,{kind:'number',min:0,max:0}),true);
});
test('universal table date ranges search and sort do not mutate source data',()=>{
  const view={...blankView(columns),filters:{date:{kind:'date',min:'2026-09-02',max:'2026-09-03'}},sort:{key:'r',direction:'desc'}};
  assert.deepEqual(tableRows(rows,columns,view).map(r=>r.id),[3,2]);assert.deepEqual(rows.map(r=>r.id),[1,2,3,4]);
  assert.deepEqual(tableRows(rows,columns,{...blankView(columns),search:'alpha'}).map(r=>r.id),[1]);
});
test('persisted table preferences retain column ordering density filters and sorting; reset restores defaults',()=>{
  const saved=JSON.parse(JSON.stringify({...blankView(columns),columns:['r','name'],order:['r','name','type'],density:'comfortable',filters:{type:['BUY']},sort:{key:'r',direction:'desc'}}));
  const view=normalizeView(saved,columns);assert.equal(view.density,'comfortable');assert.deepEqual(view.order,['r','name','type','date']);assert.deepEqual(view.columns,['r','name']);assert.deepEqual(view.filters,{type:['BUY']});
  const reset=blankView(columns);assert.equal(reset.density,'compact');assert.deepEqual(reset.filters,{});assert.deepEqual(reset.columns,['name','type','r']);
  assert.deepEqual(normalizeView({columns:['removed'],order:['removed']},columns).columns,reset.columns);
});
test('Calendar weekly counts and currency totals are additive; mixed currency signs remain neutral',()=>{
  const days=[{trades:3,wins:1,losses:1,total_r:1,pnl_by_currency:[{currency:'USD',total_pnl:10}]},{trades:1,wins:1,losses:0,total_r:2,pnl_by_currency:[{currency:'GBP',total_pnl:20}]}];
  const w=weeklySummary(days);assert.equal(w.trades,4);assert.equal(w.total_r,3);assert.ok(Math.abs(w.win_rate-200/3)<1e-10);assert.equal(w.pnl_by_currency.length,2);
  assert.equal(calendarTone(days[0]),'positive');assert.equal(calendarTone({pnl_by_currency:[{currency:'USD',total_pnl:10},{currency:'GBP',total_pnl:-5}]}),'neutral');assert.equal(weeklySummary([]).total_r,null);
});


test('legacy Journal and Runs preferences migrate without replacing newer views',async()=>{
  const {initialTableView}=await import('../src/components/table/tableModel.js');
  const saved={'ledger.journal.tableColumns.v1':['r','name'],'ledger.ui.runs.filters':{type:['BUY']}};
  const storage={getItem:key=>JSON.stringify(saved[key]??null)};
  assert.deepEqual(initialTableView('journal',columns,{},storage).columns,['r','name']);
  assert.deepEqual(initialTableView('runs',columns,{},storage).filters,{type:['BUY']});
  saved['ledger.ui.table.journal']={...blankView(columns),columns:['type']};
  assert.deepEqual(initialTableView('journal',columns,{},storage).columns,['type']);
});
