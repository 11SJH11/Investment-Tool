import test from 'node:test';
import assert from 'node:assert/strict';
import {createInvalidator} from '../src/components/chart/drawings/invalidation.js';
import {nearestOHLC,translatePoints,constrainPoint,marketTimeToLogical,logicalToMarketTime,translatePointsLogical,logicalToCoordinateInterpolated} from '../src/components/chart/drawings/geometry.js';
import {seriesChange} from '../src/components/chart/seriesUpdates.js';
import {createRequestCache,stableKey} from '../src/api/chartRequests.js';
test('drawing invalidation coalesces events and never schedules an idle loop',()=>{let scheduled=[],n=0,cancelled=[];const s=createInvalidator(()=>n++,f=>(scheduled.push(f),scheduled.length),id=>cancelled.push(id));s.invalidate();s.invalidate();assert.equal(scheduled.length,1);scheduled[0]();assert.equal(n,1);assert.equal(scheduled.length,1);s.invalidate();s.dispose();scheduled[1]();assert.equal(n,1);assert.deepEqual(cancelled,[2]);});
test('magnet checks nearest logical bar and four OHLC prices only',()=>{const bar={timestamp:'2026-09-01T10:00:00Z',open:10,high:12,low:9,close:11};let reads=0;const bars=new Proxy(Array(10000).fill(bar),{get:(a,k)=>{if(/^\d+$/.test(String(k)))reads++;return a[k];}});const p={time:1,price:5};const args={point:p,logical:5000.2,bars,toX:i=>i,toY:p=>p*10,x:5000,y:111,mode:'weak'};assert.equal(nearestOHLC(args).price,11);assert.equal(reads,1);assert.equal(nearestOHLC({...args,y:200}),p);assert.equal(nearestOHLC({...args,mode:'strong',y:200}).price,12);assert.equal(nearestOHLC({...args,mode:'off'}),p);});

test('cross-timeframe drawing projection interpolates integer bar coordinates instead of collapsing to x=0',()=>{
 const fiveMinuteTimes=[0,300,600];
 const logical=marketTimeToLogical(fiveMinuteTimes,60,300);
 assert.equal(logical,0.2);
 // Mirrors Lightweight Charts 5.x: non-integer logical indexes resolve to 0,
 // while integer bar indexes have valid pixel coordinates.
 const libraryLogicalToCoordinate=index=>Number.isInteger(index)?100+index*50:0;
 assert.equal(libraryLogicalToCoordinate(logical),0);
 assert.equal(logicalToCoordinateInterpolated(logical,libraryLogicalToCoordinate),110);
});

test('off-grid anchors retain proportional placement when moving from 1m to 15m',()=>{
 const times=[0,900,1800];
 const logical=marketTimeToLogical(times,120,900);
 assert.ok(Math.abs(logical-(120/900))<1e-12);
 const x=logicalToCoordinateInterpolated(logical,index=>40+index*120);
 assert.ok(Math.abs(x-56)<1e-9);
});
test('whole drawing translation preserves market coordinates without mutating originals',()=>{const p=[{time:100,price:20},{time:160,price:25}];assert.deepEqual(translatePoints(p,{time:0,price:0},{time:60,price:2}),[{time:160,price:22},{time:220,price:27}]);assert.equal(p[0].time,100);const q=constrainPoint({time:0,price:0},{time:10,price:1},p=>({x:p.time,y:p.price}),(x,y)=>({time:x,price:y}));assert.equal(q.price,0);});

test('drawing projection treats overnight/session gaps as compressed logical gaps',()=>{
 const step=300,times=[0,300,600,60_000,60_300];
 assert.equal(marketTimeToLogical(times,300,step),1);
 assert.ok(marketTimeToLogical(times,840,step)>2&&marketTimeToLogical(times,840,step)<3,'near close remains near left session edge');
 assert.ok(marketTimeToLogical(times,59_760,step)>2&&marketTimeToLogical(times,59_760,step)<3,'near next open remains near right session edge');
 const middle=logicalToMarketTime(times,2.5,step);
 assert.ok(middle<=900||middle>=59_700,'logical midpoint never becomes a synthetic overnight timestamp');
});
test('whole drawing drag translates by logical bars instead of wall-clock closure length',()=>{
 const times=[0,60,120,3600,3660];
 const points=[{time:60,price:10},{time:120,price:12}];
 const logicals=points.map(p=>marketTimeToLogical(times,p.time,60));
 const moved=translatePointsLogical(points,logicals,1,2,l=>logicalToMarketTime(times,l,60));
 assert.deepEqual(moved,[{time:120,price:12},{time:3600,price:14}]);
 assert.equal(moved[1].time,3600,'one logical bar crosses directly to the next available session bar');
});
test('series updates append/latest but replace history corrections, prepend and rewind',()=>{const a=[{time:1,close:1},{time:2,close:2}];assert.equal(seriesChange(a,[...a,{time:3,close:3}]).mode,'update');assert.equal(seriesChange(a,[a[0],{time:2,close:4}]).mode,'update');assert.equal(seriesChange(a,[{time:1,close:5},a[1]]).mode,'replace');assert.equal(seriesChange(a,[a[0]]).mode,'replace');assert.equal(seriesChange(a,[{time:0,close:0},...a]).mode,'replace');});
test('chart cache shares pending requests, reuses responses and bypasses on refresh',async()=>{let calls=0,now=0;const c=createRequestCache({now:()=>now,ttl:10});const load=()=>++calls;const a=c.get('x',load),b=c.get('x',load);assert.equal(a,b);assert.equal(await a,1);assert.equal(await c.get('x',load),1);assert.equal(await c.get('x',load,{refresh:true}),2);now=20;assert.equal(await c.get('x',load),3);c.clear();assert.equal(await c.get('x',load),4);assert.equal(stableKey({b:2,a:1}),stableKey({a:1,b:2}));});
test('failed chart requests are not cached; late stale requests cannot erase refresh',async()=>{const c=createRequestCache();let reject;const old=c.get('x',()=>new Promise((_,r)=>reject=r));await Promise.resolve();const fresh=c.get('x',()=>2,{refresh:true});reject(Error('old'));await assert.rejects(old);assert.equal(await fresh,2);assert.equal(await c.get('x',()=>3),2);});
