import test from 'node:test';
import assert from 'node:assert/strict';
import {assignRunStyles,prepareCurve,unionDomain,pointAt,chartValue,loadRuns} from '../src/features/strategy-lab/equitySeries.js';
const points=(offset=0)=>[100,120,90,120,130].map((equity,i)=>({timestamp:new Date((1700000000+offset+i*60)*1000).toISOString(),equity,return_pct:equity-100,drawdown_pct:[0,0,-25,0,0][i],cumulative_r:i}));
for(const count of [1,2,5,10,15,30])test(`${count} runs retain complete shared domains and consistent identities`,()=>{
 const ids=Array.from({length:count},(_,i)=>i+1),styles=assignRunStyles(ids),curves=ids.map(id=>prepareCurve(points(id*600),100));
 const before=styles.get('1');assignRunStyles([...ids].reverse(),styles);assert.equal(styles.get('1'),before);
 assert.deepEqual(unionDomain(curves),{from:curves[0].start,to:curves.at(-1).end});
 for(const curve of curves){assert.equal(pointAt(curve,curve.start-1),null);assert.equal(pointAt(curve,curve.end+1),null);assert.equal(Math.min(...curve.display.map(p=>p.drawdown_pct)),-25);assert.equal(curve.rows[0].equity,100);assert.equal(curve.rows.at(-1).equity,130);}
});
test('exact plateau compression keeps edges, recovery and trade markers without smoothing drawdowns',()=>{
 const raw=[100,100,100,120,90,90,90,120,120,130].map((equity,i)=>({timestamp:new Date((1700000000+i)*1000).toISOString(),equity,drawdown_pct:equity===90?-25:0,return_pct:equity-100,cumulative_r:0,...(i===5?{closed_trades:[{r_multiple:-1}]}:{})}));
 const curve=prepareCurve(raw,100);assert.equal(curve.display[0].equity,100);assert.equal(curve.display.at(-1).equity,130);assert.equal(curve.display.find(p=>p.closed_trades)?.time,1700000005);assert.equal(Math.min(...curve.display.map(p=>p.drawdown_pct)),-25);assert.ok(curve.display.some(p=>p.time===1700000007));assert.ok(curve.display.length<raw.length);
});
test('normalized return uses each starting capital, with explicit starting balance anchor',()=>{
 const a=prepareCurve(points(),100),b=prepareCurve(points().map(p=>({...p,equity:p.equity*2})),200);assert.equal(chartValue(a.rows.at(-1),'return',100),30);assert.equal(chartValue(b.rows.at(-1),'return',200),30);
 const changed=prepareCurve(points().slice(1),100);assert.equal(changed.rows[0].return_pct,0);assert.equal(changed.rows[0].initial_anchor,true);
});
test('bounded comparison loading retains requested order',async()=>{let active=0,peak=0;const data=await loadRuns([1,2,3,4,5],async id=>{active++;peak=Math.max(peak,active);await new Promise(r=>setTimeout(r,2));active--;return id});assert.deepEqual(data,[1,2,3,4,5]);assert.ok(peak<=3)});
