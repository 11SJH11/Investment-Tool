export const finite = v => typeof v === 'number' && Number.isFinite(v) ? v : null;
export const displayDiagnostic = v => finite(v) == null ? '\u2014' : v.toFixed(2);
export const thresholds = [[.25,'0_25'],[.5,'0_5'],[1,'1'],[1.5,'1_5'],[2,'2'],[3,'3']];
export function tradeDiagnostics(trade) {
  const m=trade.metadata || trade.source_metadata || {};
  const mfe=finite(m.mfe_r) ?? finite(m.mfe_r_lower_bound), mae=finite(m.mae_r) ?? finite(m.mae_r_lower_bound);
  const elapsed=trade.entry_time && trade.exit_time ? (Date.parse(trade.exit_time)-Date.parse(trade.entry_time))/60000 : NaN;
  const minutes=finite(m.minutes_in_trade) ?? (elapsed>=0 && Number.isFinite(elapsed)?elapsed:null);
  const result=finite(trade.r_multiple);
  // Metadata must not override execution facts when diagnostics join a trade.
  const extra=['mfe_price','mae_price','mfe_time','mae_time','time_to_mfe_minutes','time_to_mae_minutes','bars_in_trade','excursion_measurement','excursion_timing',...thresholds.map(([,key])=>`time_to_${key}r`)];
  return {...Object.fromEntries(extra.map(key=>[key,m[key]??null])),mfe_r:mfe,mae_r:mae,minutes_in_trade:minutes,giveback_r:mfe!=null&&result!=null?mfe-result:null};
}
const values = (rows,key) => rows.map(r=>finite(r[key])).filter(v=>v!=null);
export const average = xs => xs.length ? xs.reduce((a,b)=>a+b,0)/xs.length : null;
export const median = xs => {const a=[...xs].sort((a,b)=>a-b),n=a.length;return n?(a[Math.floor(n/2)]+a[Math.floor((n-1)/2)])/2:null;};
export function breakdownDiagnostics(trades,dimension,key) {
  // Time buckets keep the engine's timezone semantics; don't guess legacy config.
  const supported=['symbol','direction','exit_reason','signal_reason','session'];
  if(!supported.includes(dimension))return null;
  return sampleStats(trades.filter(t=>String(dimension==='session'?t.metadata?.session||'unlabelled':dimension==='signal_reason'?t.signal_reason||'unspecified':t[dimension])===String(key)).map(t=>({...t,...tradeDiagnostics(t)})));
}
export function sampleStats(rows) {
  const rs=values(rows,'r_multiple'), wins=rs.filter(r=>r>0),losses=rs.filter(r=>r<0),total=xs=>xs.reduce((a,b)=>a+b,0);
  const exitCounts={}; for(const r of rows)exitCounts[r.exit_reason||'Unknown']=(exitCounts[r.exit_reason||'Unknown']||0)+1;
  const count=pattern=>rows.filter(r=>pattern.test(r.exit_reason||'')).length;
  return {n:rows.length,r_n:rs.length,win_rate:rs.length?100*wins.length/rs.length:null,average_r:average(rs),total_r:rs.length?total(rs):null,profit_factor:losses.length?total(wins)/-total(losses):null,
    average_mfe:average(values(rows,'mfe_r')),average_mae:average(values(rows,'mae_r')),average_hold:average(values(rows,'minutes_in_trade')),
    mfe_n:values(rows,'mfe_r').length,mae_n:values(rows,'mae_r').length,hold_n:values(rows,'minutes_in_trade').length,
    stop:count(/stop/),target:count(/target|take_profit/),session_close:count(/session_close/),exitCounts};
}
export function excursionAnalysis(trades) {
  const rows=trades.map(t=>({...t,...tradeDiagnostics(t),r_multiple:finite(t.r_multiple)}));
  const mfe=rows.filter(r=>finite(r.mfe_r)!=null),mae=rows.filter(r=>finite(r.mae_r)!=null),rs=values(rows,'r_multiple');
  const buckets=(sample,key,bounds)=>bounds.map((low,i)=>{const high=bounds[i+1]??Infinity, group=sample.filter(r=>r[key]>=low&&r[key]<high);return {...sampleStats(group),label:high===Infinity?`${low}R+`:low===0?`< ${high}R`:`${low}\u2013${high}R`,percent:sample.length?100*group.length/sample.length:null};});
  const summary=sampleStats(rows);
  let drawdown=null;
  // Complete exit ordering and R coverage are required; ties net together.
  if(rows.length && rows.every(r=>finite(r.r_multiple)!=null&&r.exit_time&&Number.isFinite(Date.parse(r.exit_time)))) {
    const groups=new Map();for(const r of rows){const t=Date.parse(r.exit_time);groups.set(t,(groups.get(t)||0)+r.r_multiple);}
    let sum=0,peak=0;drawdown=0;for(const [,r] of [...groups].sort((a,b)=>a[0]-b[0])){sum+=r;peak=Math.max(peak,sum);drawdown=Math.max(drawdown,peak-sum);}
  }
  return {summary:{...summary,median_mfe:median(values(mfe,'mfe_r')),median_mae:median(values(mae,'mae_r')),median_hold:median(values(rows,'minutes_in_trade')),average_winner:average(rs.filter(r=>r>0)),average_loser:average(rs.filter(r=>r<0)),median_r:median(rs),drawdown_r:drawdown},
    mfe:buckets(mfe,'mfe_r',[0,.25,.5,1,1.5,2,3]),mae:buckets(mae,'mae_r',[0,.25,.5,.75,1]),
    thresholds:thresholds.map(([threshold,key])=>{const group=mfe.filter(r=>r.mfe_r>=threshold),times=values(group,`time_to_${key}r`);return {...sampleStats(group),label:`\u2265 ${threshold}R`,percent:mfe.length?100*group.length/mfe.length:null,time_n:times.length,average_time:average(times),median_time:median(times)};}),
    reversals:[.5,1,1.5].map(threshold=>({threshold,n:mfe.filter(r=>r.mfe_r>=threshold&&r.r_multiple!=null&&r.r_multiple<=0).length})),
    stoppedAfterOne:mfe.filter(r=>r.mfe_r>=1&&r.r_multiple!=null&&Math.abs(r.r_multiple+1)<=.05&&/stop/.test(r.exit_reason||'')).length};
}
