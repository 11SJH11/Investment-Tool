import {tradeDiagnostics} from '../features/strategy-lab/tradeDiagnostics.js';
import {safeFilename} from './csv.js';

export const diagnosticFields=['mfe_r','mae_r','mfe_price','mae_price','mfe_time','mae_time','time_to_mfe_minutes','time_to_mae_minutes','time_to_0_25r','time_to_0_5r','time_to_1r','time_to_1_5r','time_to_2r','time_to_3r','giveback_r','bars_in_trade','minutes_in_trade','excursion_measurement','excursion_timing'];
const tradeFields=['symbol','direction','entry_time','entry_price','stop_loss','take_profit','exit_time','exit_price','exit_reason','planned_rr','r_multiple','net_pnl','result'];
export function backtestExportRows(result,trades=result.trades||[]) {
  return trades.map(t=>{
    const diagnostics=tradeDiagnostics(t),metadata=t.metadata||{};
    return {run_id:result.saved_run?.id,run_name:result.saved_run?.name||result.run_name,strategy_key:result.strategy?.key,strategy_name:result.strategy?.name,strategy_version:result.strategy?.version,
      ...Object.fromEntries(tradeFields.map(k=>[k,t[k]??null])),...Object.fromEntries(Object.entries(t).filter(([k])=>k!=='metadata')),
      ...Object.fromEntries(diagnosticFields.map(k=>[k,diagnostics[k]??null])),
      ...Object.fromEntries(Object.keys(metadata).sort().filter(k=>metadata[k]==null||typeof metadata[k]!=='object').map(k=>['meta_'+k,metadata[k]])),metadata_json:metadata};
  });
}
export function runExportFilename(result,suffix) {
  const start=(result.start_date||result.start||result.data?.requested_start||'').slice(0,10),end=(result.end_date||result.end||result.data?.requested_end||'').slice(0,10);
  return safeFilename(`ledger-backtest-${result.saved_run?.id??'unsaved'}-${(result.symbols||[]).join('-')}-${result.strategy?.key||'strategy'}`).slice(0,110)+`-${start}_${end}-${suffix}`;
}
export function journalExportRow(t) {
  const d=tradeDiagnostics({...t,metadata:t.source_metadata,entry_time:t.opened_at,exit_time:t.closed_at});
  return {...t,...Object.fromEntries(diagnosticFields.map(k=>[k,d[k]??null]))};
}
export const portfolioExportRows=(rows,context={})=>rows.map(row=>({...context,...row}));
