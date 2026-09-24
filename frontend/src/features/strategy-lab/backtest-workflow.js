export const RUN_TYPES = ['Single backtest', 'Validation suite', 'Sensitivity test'];
export function configurationError(payload) {
  if(!String(payload.run_name||'').trim())return 'Run name is required.';
  if(!payload.symbols?.length)return 'Choose at least one symbol.';
  if(!payload.start_date||!payload.end_date||payload.start_date>payload.end_date)return 'Choose a valid start and end date.';
  for(const key of ['starting_balance','risk_value','max_leverage','max_open_positions'])if(!Number.isFinite(payload[key])||payload[key]<=0)return `${key.replaceAll('_',' ')} must be positive.`;
  for(const key of ['commission_per_order','slippage_bps','spread_bps'])if(!Number.isFinite(payload[key])||payload[key]<0)return 'Costs must be zero or positive.';
  if(!payload.trading_weekdays?.length)return 'Choose at least one trading day.';
  return '';
}
export function nextRunName(runs=[]) {
  const highest=runs.reduce((max,run)=>Math.max(max,Number(run?.id)||0),0);
  return `Run ${highest+1}`;
}
export function parseSymbols(value) { return [...new Set(String(value).toUpperCase().split(/[\s,;]+/).filter(Boolean))]; }
export function independentRuns(payload) {
  return payload.symbols.map(symbol=>({...payload, symbols:[symbol], experiment_group:payload.experiment_group&&payload.symbols.length>1?`${payload.experiment_group}-${symbol}`:payload.experiment_group||'', run_name:payload.symbols.length>1?`${payload.run_name||payload.strategy_key} · ${symbol}`:payload.run_name}));
}
export function queueCounts(jobs) { return jobs.reduce((out,job)=>({...out,[job.status]:(out[job.status]||0)+1}),{}); }
export function runSummary(payload) {
  const isNonEquity=s=>/^(XAU_?USD|[A-Z][A-Z0-9]{0,4}[1-9]!|[A-Z][A-Z0-9]{0,4}[FGHJKMNQUVXZ]\d{1,2})$/.test(s);
  const sessions=[...new Set(payload.symbols.map(s=>isNonEquity(s)?'24h':'regular'))];
  const session = payload.session==='auto' ? sessions.join(' / ')+' (per instrument)' : payload.session;
  return {
    Run: payload.run_name, Instruments: payload.symbols.join(' · '), Timeframe:payload.primary_timeframe,
    Period:`${payload.start_date} → ${payload.end_date}`,
    Balance:`$${payload.starting_balance.toLocaleString('en-US')} per independent run`,
    Sizing:`${payload.sizing_mode.replaceAll('_',' ')} · ${payload.risk_value}`,
    Costs:`$${payload.commission_per_order}/order · ${payload.slippage_bps} bps slippage · ${payload.spread_bps} bps spread`,
    Session:session,
    Execution:`${payload.same_bar_policy.replaceAll('_',' ')} · leverage cap ${payload.max_leverage}×`,
  };
}
export function filterRuns(runs, filters={}, sort={key:'created_at', direction:'desc'}) {
  const filtered=runs.filter(run=>Object.entries(filters).every(([key,rule])=>{
    if(!rule) return true;
    const value=key==='status'?'completed':run[key];
    if(Array.isArray(rule)) return !rule.length||rule.some(v=>Array.isArray(value)?value.includes(v):String(value)===v);
    if(typeof rule==='object') {
      if(value==null) return !rule.min&&!rule.max;
      if(rule.kind==='number') {
        if(rule.operator==='greater')return rule.min===''||rule.min==null||Number(value)>Number(rule.min);
        if(rule.operator==='less')return rule.max===''||rule.max==null||Number(value)<Number(rule.max);
        return (rule.min===''||rule.min==null||Number(value)>=Number(rule.min))&&(rule.max===''||rule.max==null||Number(value)<=Number(rule.max));
      }
      return (!rule.min||String(value).slice(0,10)>=rule.min)&&(!rule.max||String(value).slice(0,10)<=rule.max);
    }
    return String(value??'').toLowerCase().includes(String(rule).toLowerCase());
  }));
  return filtered.sort((a,b)=>{const x=a[sort.key],y=b[sort.key];return (typeof x==='number'&&typeof y==='number'?x-y:String(x??'').localeCompare(String(y??'')))*(sort.direction==='asc'?1:-1);});
}
