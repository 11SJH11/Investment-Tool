export const isGoldReference = (run) => ["xau_liquidity_type3_baseline_v1", "xau_type3_experiment_reference_v1"].includes(run.result?.strategy?.key);
const finite = (x) => x != null && Number.isFinite(Number(x));
const average = (xs) => xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
const numbers = (xs) => xs.filter(finite).map(Number);
const identity = (s) => {
  const m = s.metadata || {};
  return m.sweep_time && m.type3_confirmation_time ? JSON.stringify([s.symbol, s.direction, m.sweep_time, m.type3_confirmation_time]) : null;
};

export function tradeStatistics(trades) {
  const rs = numbers(trades.map(t => t.r_multiple));
  const mfes = numbers(trades.map(t => t.metadata?.mfe_r));
  const maes = numbers(trades.map(t => t.metadata?.mae_r));
  const holds = numbers(trades.map(t => {
    const minutes = (Date.parse(t.exit_time) - Date.parse(t.entry_time)) / 60000;
    return Number.isFinite(minutes) && minutes >= 0 ? minutes : null;
  }));
  const positive = rs.reduce((a, r) => a + Math.max(0, r), 0);
  const negative = rs.reduce((a, r) => a + Math.max(0, -r), 0);
  return { n: trades.length, r_n: rs.length, win_rate: trades.length ? 100 * trades.filter(t => t.result === "win").length / trades.length : null,
    average_r: average(rs), total_r: rs.length ? rs.reduce((a, b) => a + b, 0) : null,
    profit_factor_r: negative ? positive / negative : positive ? "No losses" : null,
    average_mfe_r: average(mfes), mfe_n: mfes.length, average_mae_r: average(maes), mae_n: maes.length,
    average_hold_minutes: average(holds), pnl: trades.length ? numbers(trades.map(t => t.net_pnl)).reduce((a, b) => a + b, 0) : null };
}

export function retention(run, reference) {
  const unavailable = { retained_pct: null, removed_pct: null, unmatched_baseline: null, extra_setups: null };
  if (!reference || !isGoldReference(reference)) return { ...unavailable, warning: "Select a Gold baseline reference for retention." };
  const signature = reference.result?.data?.comparison_signature;
  if (!signature || signature !== run.result?.data?.comparison_signature) return { ...unavailable, warning: "Input data, parameters or execution settings differ, or fingerprints are unavailable; retention is unavailable." };
  const base = reference.result?.setups || [];
  const other = run.result?.setups || [];
  if ([...base, ...other].some(s => !identity(s))) return { ...unavailable, warning: "Setup identities are incomplete." };
  const baseline = new Set(base.map(identity));
  const candidates = new Map(other.map(s => [identity(s), s]));
  let retained = 0, removed = 0, unmatched = 0;
  for (const id of baseline) {
    const setup = candidates.get(id);
    if (!setup) unmatched++;
    else if (setup.metadata?.filters_passed === false) removed++;
    else if (setup.metadata?.filters_passed === true || isGoldReference(run)) retained++;
    else unmatched++;
  }
  return { retained_pct: baseline.size ? retained / baseline.size * 100 : null,
    removed_pct: baseline.size ? removed / baseline.size * 100 : null,
    unmatched_baseline: unmatched, extra_setups: [...candidates.keys()].filter(id => !baseline.has(id)).length,
    warning: unmatched ? "Position occupancy changed the observed setup cohort; unmatched setups are not counted as removed." : "" };
}

export function comparison(run, reference) {
  const result = run.result || {}, trades = result.trades || [], setups = result.setups || [];
  const key = result.strategy?.key || "";
  const unsupported = key.startsWith("xau_type3_experiment_") && (key.includes("dxy") || key.includes("full_candidate"));
  const summary = { ...tradeStatistics(trades), detected_setups: setups.length,
    rejected_setups: setups.filter(s => ["rejected", "filtered"].includes(s.status)).length,
    unfilled_setups: setups.filter(s => s.status === "not_filled").length,
    fill_rate: setups.length ? 100 * setups.filter(s => s.status === "filled").length / setups.length : null,
    max_drawdown_pct: result.metrics?.max_drawdown_pct ?? null,
    consecutive_losses: result.metrics?.longest_losing_streak ?? null,
    pnl: result.metrics?.net_pnl ?? null, ...retention(run, reference) };
  if (unsupported) {
    for (const metric of ["win_rate", "average_r", "total_r", "profit_factor_r", "max_drawdown_pct", "consecutive_losses", "pnl"]) summary[metric] = null;
    summary.warning = "DXY data unavailable: no performance conclusion is possible. " + summary.warning;
  }
  const groups = Object.fromEntries(["session", "direction", "weekday", "month", "year", "regime"].map(k => [k, {}]));
  for (const trade of trades) {
    const date = new Date(trade.entry_time);
    const valid = Number.isFinite(date.getTime());
    const part = (options) => valid ? new Intl.DateTimeFormat("en-GB", { timeZone: "America/New_York", ...options }).format(date) : "Unavailable";
    const values = {session: trade.metadata?.session || "Unavailable", direction: trade.direction,
      weekday: part({ weekday: "long" }), month: part({year:"numeric",month:"2-digit"}),
      year: part({year:"numeric"}), regime: trade.metadata?.regime || "Unavailable"};
    for (const [dimension, value] of Object.entries(values)) (groups[dimension][value] ||= []).push(trade);
  }
  return { summary, breakdowns: Object.fromEntries(Object.entries(groups).map(([key, group]) =>
    [key, Object.entries(group).map(([label, rows]) => ({ label, ...tradeStatistics(rows) }))])) };
}
