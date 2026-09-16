export const sourceLabels = { live_manual: "Live · manual", paper_manual: "Paper · manual", replay: "Replay · automatic", backtest: "Backtest · automatic" };
sourceLabels.broker_oanda = "OANDA · imported";
export function sourceLabel(source) { return sourceLabels[source] || String(source || "Unknown source").replace(/^broker_/, "Broker · ").replaceAll("_", " "); }
export function pnlSummary(summary) { const rows = summary?.pnl_by_currency || []; return rows.length ? rows.map(r => moneyCurrency(r.total_pnl, r.currency)).join(" · ") : "—"; }
export function journalToday(zone) { const parts = new Intl.DateTimeFormat("en-CA", {timeZone:zone, year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(new Date()); const value=k=>parts.find(p=>p.type===k).value; return `${value("year")}-${value("month")}-${value("day")}`; }
export function money(v) { return moneyCurrency(v, "USD"); }
export function moneyCurrency(v, currency = "USD") { if(v==null||v==="")return "\u2014";try{return Intl.NumberFormat("en-GB",{style:"currency",currency,maximumFractionDigits:2}).format(Number(v));}catch{return `${currency} ${Number(v).toFixed(2)}`;} }
export function pct(v) { return v == null || v === "" ? "—" : `${Number(v).toFixed(2)}%`; }
export function rValue(v) { return v == null || v === "" ? "—" : `${Number(v).toFixed(2)}R`; }
export function rrValue(v) { return v == null || v === "" ? "—" : `${Number(v).toFixed(2)}:1`; }
export function localInputNow() { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 16); }
export function today() { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0,10); }
export function resultTone(result) { return result === "win" ? "text-emerald-700" : result === "loss" ? "text-red-700" : result === "breakeven" ? "text-amber-700" : "text-stone-500"; }
