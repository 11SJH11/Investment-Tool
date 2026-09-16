export function splitOptions(text) {
  return [...new Set(String(text).split(/[\n,/]+/).map(v => v.trim()).filter(Boolean))];
}
export function moveOption(options, index, delta) {
  const target = index + delta;
  if (target < 0 || target >= options.length) return [...options];
  const result = [...options];
  [result[index], result[target]] = [result[target], result[index]];
  return result;
}
export const TABLE_COLUMNS = [
  ['opened_at','Date/time'],['ticker','Instrument'],['direction','Direction'],['quantity','Quantity / size'],
  ['entry_price','Entry'],['exit_price','Exit'],['pnl_amount','P&L'],['currency','Currency'],['r_multiple','R'],
  ['source','Source'],['external_provider','Broker'],['account','Account'],['environment','Environment'],
  ['playbook_title','Playbook'],['setup','Setup'],['setup_grade','Grade'],['plan_followed','Plan adherence'],
  ['session_time','Session'],['market_condition','Market regime'],['duration','Duration (min)'],['exit_reason','Exit reason'],
];
export const DEFAULT_COLUMNS = ['opened_at','ticker','direction','quantity','entry_price','exit_price','pnl_amount','currency','r_multiple','source','account','setup_grade'];
const KEY = 'ledger.journal.tableColumns.v1';
export function loadColumns(storage) {
  try {
    const saved = JSON.parse(storage.getItem(KEY));
    const allowed = new Set(TABLE_COLUMNS.map(([key]) => key));
    const values = Array.isArray(saved) ? [...new Set(saved.filter(v => allowed.has(v)))] : [];
    return values.length ? values : [...DEFAULT_COLUMNS];
  } catch { return [...DEFAULT_COLUMNS]; }
}
export function saveColumns(storage, columns) {
  try { storage.setItem(KEY, JSON.stringify(columns)); } catch { /* Storage may be disabled. */ }
}
