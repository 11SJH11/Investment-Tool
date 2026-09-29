import test from 'node:test';
import assert from 'node:assert/strict';
import {csvCell,toCsv,tableExportRows,downloadCsv,downloadJson} from '../src/utils/csv.js';
import {backtestExportRows,journalExportRow,portfolioExportRows} from '../src/utils/researchExports.js';
import {tradeDiagnostics,displayDiagnostic,excursionAnalysis,breakdownDiagnostics} from '../src/features/strategy-lab/tradeDiagnostics.js';

test('CSV escapes quotes, commas, newline, Unicode and nested data',()=>{
  assert.equal(csvCell('a,"b"\nc'), '"a,""b""\nc"');
  assert.equal(csvCell(null),'');assert.equal(csvCell(NaN),'');assert.equal(csvCell(-1.5),'-1.5');
  assert.equal(csvCell({a:['£',2]}),'"{""a"": [""£"",2]}"'.replace(': ',':'));
  assert.equal(toCsv([{z:1,a:2},{b:3}]).split('\r\n')[0],'"a","b","z"');
});
test('spreadsheet formulas guarded, including numeric-looking strings and leading spaces',()=>{
  for(const value of ['=SUM(A1)','+1','-1','@x','\tfoo','\rfoo','  =1'])assert.ok(csvCell(value).startsWith('"\''));
  assert.equal(csvCell(0),'0');assert.equal(csvCell(-2),'-2');
});
test('legacy diagnostics normalize aliases without inventing zero measurements',()=>{
  const t={entry_time:'2026-01-01T00:00Z',exit_time:'2026-01-01T00:12Z',r_multiple:-1,metadata:{mfe_r_lower_bound:1.86,mae_r_lower_bound:.5}};
  const d=tradeDiagnostics(t);assert.equal(d.mfe_r,1.86);assert.equal(d.mae_r,.5);assert.equal(d.minutes_in_trade,12);assert.ok(Math.abs(d.giveback_r-2.86)<1e-9);
  for(const key of ['mfe_r','mae_r','minutes_in_trade','giveback_r'])assert.equal(displayDiagnostic(tradeDiagnostics({})[key]),'\u2014');
  assert.equal(tradeDiagnostics({r_multiple:null,metadata:{mfe_r:1}}).giveback_r,null);
  assert.equal(displayDiagnostic(0),'0.00');assert.equal(displayDiagnostic(Infinity),'\u2014');
});
test('all matching rows export before pagination, without using JSX or changing selection',()=>{
  const rows=Array.from({length:75},(_,id)=>({id,value:id,selected:id===1}));const before=structuredClone(rows);
  const matching=rows.filter(r=>r.value>=20).sort((a,b)=>b.value-a.value);
  const out=tableExportRows(matching,[{key:'value',render:()=>{throw Error('JSX renderer used');}}]);
  assert.equal(out.length,55);assert.equal(out[0].value,74);assert.equal(toCsv(out).split('\r\n').length,56);assert.deepEqual(rows,before);
  assert.deepEqual(tableExportRows([{value:-2}],['value']),[{value:-2}]);
});
test('run all and filtered export retain facts, metadata and immutable snapshot',()=>{
  const run={saved_run:{id:93,name:'Research'},strategy:{key:'any',name:'Any',version:'1'},trades:Array.from({length:25},(_,id)=>({id,r_multiple:-1,metadata:{mfe_r:1.5,session:'cash',nested:{a:1}}}))};
  const before=structuredClone(run),all=backtestExportRows(run),filtered=backtestExportRows(run,run.trades.slice(5));
  assert.equal(all.length,25);assert.equal(filtered.length,20);assert.equal(all[0].giveback_r,2.5);assert.equal(all[0].meta_session,'cash');assert.equal(all[0].strategy_version,'1');
  assert.ok(!toCsv(all).includes('[object Object]'));assert.deepEqual(run,before);
});
test('Journal and Portfolio preserve notes, raw values and currencies',()=>{
  const journal=journalExportRow({id:1,notes:'=note',source_metadata:{mfe_r_lower_bound:2},review_data:{custom:3},r_multiple:null});
  assert.equal(journal.mfe_r,2);assert.equal(journal.giveback_r,null);assert.deepEqual(journal.review_data,{custom:3});assert.ok(!toCsv([journal]).includes('[object Object]'));
  const holdings=portfolioExportRows([{quantity:1.25,value:30,currency:'EUR',facts:{price:30}}],{account:'demo'});
  assert.equal(holdings[0].quantity,1.25);assert.equal(holdings[0].currency,'EUR');assert.equal(holdings[0].account,'demo');
});
test('excursion buckets, thresholds, samples and closed-trade drawdown',()=>{
  const trades=[{symbol:'A',r_multiple:2,exit_reason:'take_profit',exit_time:'2026-01-01',metadata:{mfe_r:2,mae_r:.25,time_to_1r:4}},{symbol:'A',r_multiple:-1,exit_reason:'stop_loss',exit_time:'2026-01-02',metadata:{mfe_r:1.5,mae_r:1,time_to_1r:6}},{r_multiple:0,exit_reason:'session_close',exit_time:'2026-01-03'}];
  const a=excursionAnalysis(trades);assert.equal(a.summary.mfe_n,2);assert.equal(a.summary.average_mfe,1.75);assert.equal(a.summary.drawdown_r,1);assert.equal(a.thresholds[2].n,2);assert.equal(a.thresholds[2].average_time,5);assert.equal(a.thresholds[2].stop,1);assert.equal(a.stoppedAfterOne,1);assert.equal(a.reversals[2].n,1);
  assert.equal(a.mfe.find(r=>r.label==='1.5\u20132R').n,1);assert.equal(a.mae.at(-1).n,1);
  assert.equal(excursionAnalysis([{}]).summary.drawdown_r,null);assert.equal(excursionAnalysis([]).summary.average_mfe,null);
  assert.equal(breakdownDiagnostics(trades,'symbol','A').mfe_n,2);
  assert.equal(excursionAnalysis([{r_multiple:-1,exit_reason:'stop_loss',metadata:{mfe_r:1,exit_reason:'take_profit',r_multiple:2}}]).thresholds[2].stop,1);
});
test('downloads preserve full JSON, encode UTF-8 CSV, and revoke URLs',()=>{
  const previous={document:globalThis.document,create:URL.createObjectURL,revoke:URL.revokeObjectURL,timer:globalThis.setTimeout};
  const blobs=[],revoked=[],timers=[],links=[];
  globalThis.document={body:{appendChild(){}},createElement(){const a={click(){links.push({...a});},remove(){}};return a;}};
  URL.createObjectURL=blob=>{blobs.push(blob);return 'blob:'+blobs.length;};URL.revokeObjectURL=url=>revoked.push(url);globalThis.setTimeout=fn=>timers.push(fn);
  try {const saved={configuration:{risk:1},result:{trades:Array(30).fill({metadata:{x:1}})}};downloadJson(saved,'full.json');downloadCsv([{value:'£'}],'trades.csv');assert.equal(blobs[0].type,'application/json;charset=utf-8');assert.equal(links[0].download,'full.json');assert.equal(timers.length,2);timers.forEach(fn=>fn());assert.deepEqual(revoked,['blob:1','blob:2']);return Promise.all([blobs[0].text().then(text=>assert.deepEqual(JSON.parse(text),saved)),blobs[1].text().then(text=>assert.ok(text.includes('£')))]);
  } finally {globalThis.document=previous.document;URL.createObjectURL=previous.create;URL.revokeObjectURL=previous.revoke;globalThis.setTimeout=previous.timer;}
});
