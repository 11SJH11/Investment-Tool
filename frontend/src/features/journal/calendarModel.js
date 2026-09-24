export function calendarTone(day) {
  const values=(day?.pnl_by_currency||[]).map(r=>r.total_pnl).filter(v=>v!==0);
  if(values.length)return values.every(v=>v>0)?'positive':values.every(v=>v<0)?'negative':'neutral';
  return day?.total_r>0?'positive':day?.total_r<0?'negative':'neutral';
}
export function weeklySummary(days) {
  const money={};let trades=0,wins=0,losses=0,total=0,rCount=0;
  for(const day of days){trades+=day.trades||0;wins+=day.wins||0;losses+=day.losses||0;if(day.total_r!=null){total+=day.total_r;rCount++;}for(const p of day.pnl_by_currency||[])money[p.currency]=(money[p.currency]||0)+p.total_pnl;}
  return {trades,wins,losses,total_r:rCount?total:null,win_rate:wins+losses?wins/(wins+losses)*100:null,pnl_by_currency:Object.entries(money).map(([currency,total_pnl])=>({currency,total_pnl}))};
}
export function calendarDays(trades,month) {
  const buckets=new Map();
  for(const trade of trades||[]){const day=trade.journal_date;if(!day||!day.startsWith(`${month}-`))continue;if(!buckets.has(day))buckets.set(day,[]);buckets.get(day).push(trade);}
  return [...buckets.entries()].sort(([a],[b])=>a.localeCompare(b)).map(([day,rows])=>{
    const closed=rows.filter(t=>t.status==='closed'),wins=closed.filter(t=>t.result==='win').length,losses=closed.filter(t=>t.result==='loss').length;
    const rs=closed.map(t=>Number(t.r_multiple)).filter(Number.isFinite),money={};
    for(const t of closed){const n=Number(t.pnl_amount);if(!Number.isFinite(n))continue;const currency=t.account_currency||t.position_currency||'USD';money[currency]=(money[currency]||0)+n;}
    return {day,trades:rows.length,wins,losses,total_r:rs.length?rs.reduce((a,b)=>a+b,0):null,win_rate:wins+losses?wins/(wins+losses)*100:null,pnl_by_currency:Object.entries(money).map(([currency,total_pnl])=>({currency,total_pnl}))};
  });
}
