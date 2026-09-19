import {TABLE_COLUMNS,DEFAULT_COLUMNS} from './journalPreferences.js';
import {formatInZone} from '../../utils/timezones.js';
import {moneyCurrency,rValue,sourceLabel} from './journalUtils.js';
export function journalColumns(zone,options={}) {
  const numeric=['quantity','entry_price','exit_price','pnl_amount','r_multiple','duration'];
  return TABLE_COLUMNS.map(([key,label])=>({key,label,kind:key==='opened_at'?'date':numeric.includes(key)?'number':['setup'].includes(key)?'text':'category',hidden:!DEFAULT_COLUMNS.includes(key),sticky:key==='opened_at',options:options[key],
    value:t=>key==='opened_at'?t.journal_date:key==='currency'?t.account_currency||t.position_currency||'USD':['environment','exit_reason'].includes(key)?t.source_metadata?.[key]:key==='duration'?(t.closed_at&&t.opened_at?(Date.parse(t.closed_at)-Date.parse(t.opened_at))/60000:null):t[key],
    render:t=>key==='opened_at'?formatInZone(t.opened_at,zone):key==='pnl_amount'?moneyCurrency(t.pnl_amount,t.account_currency||t.position_currency||'USD'):key==='r_multiple'?rValue(t.r_multiple):key==='source'?sourceLabel(t.source):key==='currency'?t.account_currency||t.position_currency||'USD':['environment','exit_reason'].includes(key)?t.source_metadata?.[key]||'Unavailable':key==='duration'?t.closed_at&&t.opened_at?((Date.parse(t.closed_at)-Date.parse(t.opened_at))/60000).toFixed(1):'Unavailable':t[key]??'Unavailable'}));
}
