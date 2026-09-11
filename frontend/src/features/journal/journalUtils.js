export const sourceLabels = { live_manual: "Live · manual", paper_manual: "Paper · manual", replay: "Replay · automatic", backtest: "Backtest · automatic" };
export function money(v) { return moneyCurrency(v, "USD"); }
export function moneyCurrency(v, currency = "USD") { return v == null || v === "" ? "—" : Intl.NumberFormat("en-GB", { style: "currency", currency, maximumFractionDigits: 2 }).format(Number(v)); }
export function pct(v) { return v == null || v === "" ? "—" : `${Number(v).toFixed(2)}%`; }
export function rValue(v) { return v == null || v === "" ? "—" : `${Number(v).toFixed(2)}R`; }
export function rrValue(v) { return v == null || v === "" ? "—" : `${Number(v).toFixed(2)}:1`; }
export function localInputNow() { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 16); }
export function today() { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0,10); }
export function resultTone(result) { return result === "win" ? "text-emerald-700" : result === "loss" ? "text-red-700" : result === "breakeven" ? "text-amber-700" : "text-stone-500"; }
