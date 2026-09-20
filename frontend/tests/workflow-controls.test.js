import test from 'node:test';
import assert from 'node:assert/strict';
import {workflowContext} from '../src/app/workflow.js';
import {replayShortcut,jumpCursor} from '../src/features/strategy-lab/replayControls.js';
import {scalar,serializeScan,blankScan,saveScan} from '../src/features/screener/scanModel.js';
import {saveDrawingDefault,drawingStyle,resetDrawingDefault} from '../src/components/chart/drawings/defaults.js';
test('handoff preserves ticker and New York date across UTC midnight',()=>{
 const c=workflowContext('Replay',{ticker:'aapl',opened_at:'2026-09-02T00:10:00Z',closed_at:'2026-09-02T01:10:00Z',timeframe:'1d'});
 assert.equal(c.symbol,'AAPL');assert.equal(c.start_date,'2026-09-01');assert.equal(c.start_time,'20:10');assert.equal(c.timeframe,'5m');
 assert.equal(workflowContext('Backtest',{symbol:'NQ1!',start_date:'2026-01-01'}).start_date,'2026-01-01');
});
test('Replay shortcuts focus orders and cannot fire while typing or on repeat',()=>{
 assert.equal(replayShortcut({key:'b'},{}),'buy');assert.equal(replayShortcut({key:'ArrowRight',shiftKey:true},{}),'five');
 for(const el of [{tagName:'INPUT'},{tagName:'TEXTAREA'},{tagName:'SELECT'},{tagName:'BUTTON'},{isContentEditable:true}])assert.equal(replayShortcut({key:'c'},el),null);
 assert.equal(replayShortcut({key:'b',repeat:true},{}),null);assert.equal(replayShortcut({key:'b',ctrlKey:true},{}),null);
});
test('Replay jump returns timeline count without reading unrevealed OHLC',()=>{
 const bars=[0,1,2,3].map(n=>({timestamp:`2026-09-01T14:0${n}:00Z`,get close(){throw Error('future price read');}}));
 assert.equal(jumpCursor(bars,'2026-09-01T14:02:30Z'),3);assert.equal(jumpCursor(bars,'2026-09-01T13:59:00Z'),null);assert.equal(jumpCursor(bars,'2026-09-01T15:00:00Z'),null);
});
test('scan values, field comparisons and saved copies retain independent definitions',()=>{
 assert.equal(scalar('2.5B'),2.5e9);assert.equal(scalar('-5'),-5);assert.throws(()=>scalar('bad'));
 const q=blankScan();q.conditions=[{field:'price',operator:'>',other_field:'ema20'},{field:'market_cap',operator:'>',value:'2B'}];
 assert.equal(serializeScan(q).conditions[1].value,2e9);
 const saved=saveScan([],'Trend',q);q.conditions[1].value='9B';assert.equal(saved[0].query.conditions[1].value,'2B');
 assert.equal(saveScan(saved,'Trend',q).length,1);assert.throws(()=>saveScan(saved,' ',q));
});
test('tool defaults never copy market anchors, IDs or locked state',()=>{
 const store=new Map();globalThis.localStorage={getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)};
 saveDrawingDefault('trend',{color:'#abcdef',lineWidth:3,points:[{time:1,price:2}],id:'old',locked:true});
 assert.deepEqual(drawingStyle('trend'),{color:'#abcdef',lineWidth:3});resetDrawingDefault('trend');assert.deepEqual(drawingStyle('trend'),{});
});
