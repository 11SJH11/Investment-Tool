import {TABLE_COLUMNS,DEFAULT_COLUMNS} from './journalPreferences.js';
import {formatInZone} from '../../utils/timezones.js';
import {moneyCurrency,rValue,sourceLabel} from './journalUtils.js';

function sourceTone(source) {
  if(source==='live_manual')return 'journal-tone-live';
  if(source==='paper_manual'||source==='replay'||source==='backtest')return 'journal-tone-practice';
  if(String(source||'').startsWith('broker_'))return 'journal-tone-imported';
  return '';
}
function toneFor(key,t) {
  const value=key==='environment'?t.source_metadata?.environment:t[key];
  if(key==='result')return value==='win'?'journal-tone-win':value==='loss'?'journal-tone-loss':value==='breakeven'?'journal-tone-breakeven':'';
  if(key==='pnl_amount'||key==='r_multiple'){const n=Number(value);return Number.isFinite(n)?(n>0?'journal-tone-win':n<0?'journal-tone-loss':'journal-tone-breakeven'):'';}
  if(key==='source')return sourceTone(t.source);
  if(key==='environment')return String(value||'').toLowerCase()==='live'?'journal-tone-live':String(value||'').toLowerCase()==='practice'?'journal-tone-practice':'';
  if(key==='setup_grade')return value==='A'?'journal-tone-win':value==='B'?'journal-tone-breakeven':value==='C'?'journal-tone-loss':'';
  if(key==='plan_followed')return value==='Yes'?'journal-tone-win':value==='Partially'?'journal-tone-breakeven':value==='No'?'journal-tone-loss':'';
  return '';
}
export function journalColumns(zone,options={}) {
  const numeric=['quantity','entry_price','exit_price','pnl_amount','r_multiple','duration'];
  return TABLE_COLUMNS.map(([key,label])=>({key,label,kind:key==='opened_at'?'date':numeric.includes(key)?'number':['setup'].includes(key)?'text':'category',hidden:!DEFAULT_COLUMNS.includes(key),sticky:key==='opened_at',options:options[key],cellClass:t=>toneFor(key,t),
    value:t=>key==='opened_at'?t.journal_date:key==='currency'?t.account_currency||t.position_currency||'USD':['environment','exit_reason'].includes(key)?t.source_metadata?.[key]:key==='duration'?(t.closed_at&&t.opened_at?(Date.parse(t.closed_at)-Date.parse(t.opened_at))/60000:null):t[key],
    render:t=>key==='opened_at'?formatInZone(t.opened_at,zone):key==='pnl_amount'?moneyCurrency(t.pnl_amount,t.account_currency||t.position_currency||'USD'):key==='r_multiple'?rValue(t.r_multiple):key==='source'?sourceLabel(t.source):key==='result'?String(t.result||'Unavailable').replace(/^./,x=>x.toUpperCase()):key==='currency'?t.account_currency||t.position_currency||'USD':['environment','exit_reason'].includes(key)?t.source_metadata?.[key]||'Unavailable':key==='duration'?t.closed_at&&t.opened_at?((Date.parse(t.closed_at)-Date.parse(t.opened_at))/60000).toFixed(1):'Unavailable':t[key]??'Unavailable'}));
}
