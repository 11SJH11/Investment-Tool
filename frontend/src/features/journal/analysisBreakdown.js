const dimensionList = [
  ['playbook','Strategy / Playbook'],['setup','Setup'],['session','Session'],['entry_10min','10-minute entry bucket'],
  ['entry_30min','30-minute entry bucket'],['entry_hour','Entry hour'],['weekday','Weekday'],['emotion','Emotion'],
  ['market_condition','Market regime'],['timeframe','Entry timeframe'],['context_timeframe','Context timeframe'],['structure_alignment','Structure alignment'],
  ['entry_relativity','Entry relativity'],['shift','Shift'],['plan_followed','Plan adherence'],['setup_grade','Grade'],['direction','Direction'],
  ['mistake','Mistake'],['confluence','Confluence'],['month','Month'],['source','Source'],['account','Account'],['symbol','Instrument'],
];
export const analysisDimensions = dimensionList;

function zonedParts(value, timeZone) {
  if (!value) return {};
  try {
    const parts = new Intl.DateTimeFormat('en-GB', {
      timeZone: timeZone || 'UTC', weekday:'long', year:'numeric', month:'2-digit', day:'2-digit',
      hour:'2-digit', minute:'2-digit', hourCycle:'h23',
    }).formatToParts(new Date(value));
    return Object.fromEntries(parts.map(p=>[p.type,p.value]));
  } catch { return {}; }
}
function bucket(openedAt,timeZone,minutes) {
  const p=zonedParts(openedAt,timeZone);if(!p.hour)return 'Unknown';
  const minute=Math.floor(Number(p.minute||0)/minutes)*minutes;
  return `${p.hour}:${String(minute).padStart(2,'0')}`;
}
function valuesFor(trade,key,timeZone) {
  const review=trade.review_data||{}, p=zonedParts(trade.opened_at,timeZone);
  let value;
  if(key==='playbook')value=trade.playbook_title||'Unlinked';
  else if(key==='setup')value=trade.setup;
  else if(key==='session')value=trade.session_time;
  else if(key==='entry_10min')value=bucket(trade.opened_at,timeZone,10);
  else if(key==='entry_30min')value=bucket(trade.opened_at,timeZone,30);
  else if(key==='entry_hour')value=p.hour?`${p.hour}:00`:'Unknown';
  else if(key==='weekday')value=p.weekday;
  else if(key==='month')value=trade.journal_date?.slice(0,7)||((p.year&&p.month)?`${p.year}-${p.month}`:null);
  else if(key==='emotion')value=review.emotions||[];
  else if(key==='mistake')value=review.mistakes||[];
  else if(key==='confluence')value=review.confluences||[];
  else if(key==='market_condition')value=trade.market_condition;
  else if(key==='timeframe')value=trade.entry_timeframe;
  else if(key==='context_timeframe')value=review.context_timeframe;
  else if(key==='structure_alignment')value=review.structure_alignment;
  else if(key==='entry_relativity')value=review.entry_relativity;
  else if(key==='shift')value=review.shift;
  else if(key==='plan_followed')value=trade.plan_followed;
  else if(key==='setup_grade')value=trade.setup_grade;
  else if(key==='direction')value=trade.direction;
  else if(key==='source')value=trade.source;
  else if(key==='account')value=trade.account;
  else if(key==='symbol')value=trade.ticker;
  else if(key.startsWith('playbook_field:'))value=review.custom?.[key.slice('playbook_field:'.length)];
  const values=Array.isArray(value)?value:[value];
  return [...new Set((values.length?values:[null]).map(v=>String(v||'Unlabelled')))];
}
function combinations(parts,index=0,prefix={}) {
  if(index>=parts.length)return [prefix];
  const [key,values]=parts[index];
  return values.flatMap(value=>combinations(parts,index+1,{...prefix,[key]:value}));
}
function finiteNumber(value) {const n=Number(value);return value!==null&&value!==''&&Number.isFinite(n)?n:null;}
export function summariseTrades(trades) {
  const closed=trades.filter(t=>t.status==='closed');
  const wins=closed.filter(t=>t.result==='win').length,losses=closed.filter(t=>t.result==='loss').length;
  const rs=closed.map(t=>finiteNumber(t.r_multiple)).filter(v=>v!==null);
  const positive=rs.filter(v=>v>0).reduce((a,b)=>a+b,0),negative=-rs.filter(v=>v<0).reduce((a,b)=>a+b,0);
  const money={};
  for(const t of closed){const amount=finiteNumber(t.pnl_amount);if(amount===null)continue;const currency=t.account_currency||t.position_currency||'USD';money[currency]=(money[currency]||0)+amount;}
  return {
    trades:trades.length,r_trades:rs.length,win_rate:wins+losses?wins/(wins+losses)*100:null,
    average_r:rs.length?rs.reduce((a,b)=>a+b,0)/rs.length:null,total_r:rs.length?rs.reduce((a,b)=>a+b,0):null,
    profit_factor_r:negative?positive/negative:(positive?'inf':null),
    pnl_by_currency:Object.entries(money).sort(([a],[b])=>a.localeCompare(b)).map(([currency,total_pnl])=>({currency,total_pnl})),
  };
}
export function compositeBreakdown(trades,dimensions,timeZone) {
  const selected=(dimensions||[]).slice(0,4);if(!selected.length)return [];
  const buckets=new Map();
  for(const trade of trades||[]){
    const parts=selected.map(key=>[key,valuesFor(trade,key,timeZone)]);
    for(const values of combinations(parts)){
      const id=selected.map(key=>`${key}=${values[key]}`).join('|');
      if(!buckets.has(id))buckets.set(id,{id,values,trades:[]});
      buckets.get(id).trades.push(trade);
    }
  }
  return [...buckets.values()].map(group=>({...group,...summariseTrades(group.trades)}));
}
export function sortBreakdown(rows,sort='sample') {
  const copy=[...(rows||[])];
  const numeric=(key,direction=-1)=>copy.sort((a,b)=>direction*((Number(a[key])||0)-(Number(b[key])||0))||b.trades-a.trades);
  if(sort==='best')return numeric('average_r',-1);
  if(sort==='worst')return numeric('average_r',1);
  if(sort==='win_rate')return numeric('win_rate',-1);
  if(sort==='total_r')return numeric('total_r',-1);
  if(sort==='label')return copy.sort((a,b)=>Object.values(a.values).join(' / ').localeCompare(Object.values(b.values).join(' / ')));
  return copy.sort((a,b)=>b.trades-a.trades);
}
