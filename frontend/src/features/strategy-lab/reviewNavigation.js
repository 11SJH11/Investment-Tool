// References use the immutable saved snapshot ordinal, never filtered row positions.
export const tradeReference = (runId, index) => `Run ${runId} / Trade ${index + 1}`;
export function navigationState(trades, trade) {
  const index = trades.indexOf(trade);
  return {index, count: trades.length, previous: index > 0 ? trades[index - 1] : null,
    next: index >= 0 && index + 1 < trades.length ? trades[index + 1] : null};
}
export function navigationKey(event) {
  if (event.ctrlKey || event.altKey || event.metaKey || event.repeat || event.target?.closest?.('input,textarea,select,[contenteditable="true"],[role="textbox"]')) return null;
  return event.key?.toLowerCase() === 'j' ? 'previous' : event.key?.toLowerCase() === 'k' ? 'next' : null;
}
export function exportScope(all, filtered, selected, scope) {
  return (scope === 'all' ? all : scope === 'selected' ? all.filter((_, i) => selected.has(i)) : filtered)
    .map(trade => ({trade, index: all.indexOf(trade)}));
}
export function detailWindow(bars, timestamp, before, after) {
  if (!bars.length) return null;
  const target = Date.parse(timestamp);
  let index = bars.findIndex(b => Date.parse(b.timestamp) >= target);
  if (index < 0) index = bars.length - 1;
  return {from: Math.max(0, index - before), to: Math.min(bars.length - 1, index + after)};
}
export function researchRow(run, trade, index, review = {}) {
  const meta = trade.metadata || {};
  const row = {run_id: run.saved_run?.id, run_name: run.saved_run?.name, trade_id: tradeReference(run.saved_run?.id, index), trade_number: index + 1,
    date: trade.entry_time, symbol: trade.symbol, direction: trade.direction,
    entry_signal_time: meta.review_entry?.signal_time ?? meta.signal_time, entry_fill_time: trade.entry_time,
    exit_signal_time: meta.review_exit?.signal_time, exit_fill_time: trade.exit_time,
    entry_price: trade.entry_price, exit_price: trade.exit_price, pnl: trade.net_pnl,
    pnl_pct: trade.pnl_pct ?? null, pnl_bps: trade.pnl_pct == null ? null : trade.pnl_pct * 100,
    realised_r: trade.r_multiple, duration_minutes: (Date.parse(trade.exit_time) - Date.parse(trade.entry_time)) / 60000,
    exit_reason: trade.exit_reason, strategy_key: run.strategy?.key, strategy_provenance: JSON.stringify(run.strategy || {}),
    review_warnings: (review.warnings || []).join('; '), recorded_metadata: JSON.stringify(meta)};
  for (const [group, fields] of Object.entries(review.evidence || {})) for (const [i, field] of fields.entries()) {
    const key = `${group}.${i}.${field.label}`;
    row[key] = field.value; row[key + '.provenance'] = field.provenance; row[key + '.status'] = field.status;
  }
  return row;
}
