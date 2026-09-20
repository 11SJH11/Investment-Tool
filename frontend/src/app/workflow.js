const intraday=['1m','5m','15m','30m','1h','4h'];
export function workflowContext(target,input={}) {
 const timestamp=input.timestamp||input.opened_at||input.entry_time;
 const end=input.end||input.closed_at||input.exit_time;
 const parts=value=>{if(!value||!Number.isFinite(Date.parse(value)))return {};const p=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(value)).map(x=>[x.type,x.value]));return {date:`${p.year}-${p.month}-${p.day}`,time:`${p.hour}:${p.minute}`};};
 const start=parts(timestamp),finish=parts(end),symbol=String(input.symbol||input.ticker||'').trim().toUpperCase();
 return {...input,target,symbol,timestamp,start_date:input.start_date||start.date,end_date:input.end_date||finish.date||start.date,start_time:start.time,timeframe:target==='Replay'&&!intraday.includes(input.timeframe)?'5m':input.timeframe};
}
