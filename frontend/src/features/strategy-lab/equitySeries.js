export const CHART_PALETTE=['#60a5fa','#fb923c','#34d399','#c084fc','#f472b6','#22d3ee','#facc15','#a3e635','#f87171','#818cf8','#2dd4bf','#e879f9','#fbbf24','#38bdf8','#fb7185'];
export function assignRunStyles(ids,assigned=new Map()){
 for(const id of ids){const key=String(id);if(!assigned.has(key)){const n=assigned.size;assigned.set(key,{color:CHART_PALETTE[n%CHART_PALETTE.length],lineStyle:Math.floor(n/CHART_PALETTE.length)%3});}}
 return assigned;
}
const number=value=>value!=null&&Number.isFinite(Number(value))?Number(value):null;
export function prepareCurve(points,startingBalance){
 const byTime=new Map();for(const point of points||[]){const time=Math.floor(Date.parse(point.timestamp)/1000);if(Number.isFinite(time)&&number(point.equity)!=null)byTime.set(time,{...point,time});}
 const rows=[...byTime.values()].sort((a,b)=>a.time-b.time);
 const balance=number(startingBalance);
 if(rows.length&&balance>0&&Number(rows[0].equity)!==balance)rows.unshift({time:rows[0].time-1,equity:balance,return_pct:0,drawdown_pct:0,cumulative_r:0,initial_anchor:true});
 // Only remove interiors of exactly unchanged plateaus. No approximate sampling.
 const same=(a,b)=>['equity','drawdown_pct','return_pct','cumulative_r'].every(k=>number(a[k])===number(b[k]));
 const display=rows.filter((p,i)=>i===0||i===rows.length-1||p.closed_trades?.length||p.realized_pnl||!same(rows[i-1],p)||!same(p,rows[i+1]));
 return {rows,display,start:rows[0]?.time,end:rows.at(-1)?.time};
}
export function unionDomain(curves){const valid=curves.filter(c=>c.rows.length);return valid.length?{from:Math.min(...valid.map(c=>c.start)),to:Math.max(...valid.map(c=>c.end))}:null;}
export function pointAt(curve,time){
 if(time<curve.start||time>curve.end)return null;
 let lo=0,hi=curve.rows.length-1;while(lo<=hi){const mid=(lo+hi)>>1;if(curve.rows[mid].time<=time)lo=mid+1;else hi=mid-1;}
 return hi>=0?curve.rows[hi]:null;
}
export function chartValue(point,mode,balance){if(mode==='return')return number(point.return_pct)??(balance>0?(point.equity/balance-1)*100:null);if(mode==='r')return number(point.cumulative_r);return number(point.equity);}

export async function loadRuns(ids,fetcher,parallel=3){const results=new Array(ids.length);let next=0;await Promise.all(Array.from({length:Math.min(parallel,ids.length)},async()=>{while(next<ids.length){const index=next++;results[index]=await fetcher(ids[index]);}}));return results;}
