import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import SymbolSearch from "../../components/SymbolSearch";
import { TIMEZONE_OPTIONS, nowInZoneInput, zonedInputToIso, formatInZone } from "../../utils/timezones";
import TradeDetail from "./TradeDetail";
import { moneyCurrency, pct, resultTone, rrValue, rValue, sourceLabels } from "./journalUtils";

function blankTrade(zone = "America/New_York") {
  return { source: "live_manual", account: "Main", ticker: "", direction: "long", opened_at: nowInZoneInput(zone), closed_at: "", entry_price: "", exit_price: "", position_amount: "", position_currency: "USD", quantity: "", stop_loss: "", take_profit: "", fees: "0", pnl_override: "", override_reason: "", trade_type: "", setup: "", market_condition: "", entry_timeframe: "", timeframe_alignment: "", dxy: "", session_time: "", tf_type: "", wick: "" };
}

function pnlSummary(analytics) {
  const rows = analytics.pnl_by_currency || [];
  if (!rows.length) return "—";
  if (rows.length === 1) return moneyCurrency(rows[0].total_pnl, rows[0].currency || "USD");
  return rows.map((r) => `${r.currency} ${Number(r.total_pnl || 0).toFixed(2)}`).join(" · ");
}

export default function TradesView() {
  const [trades, setTrades] = useState([]);
  const [analytics, setAnalytics] = useState({});
  const [source, setSource] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [timeZone, setTimeZone] = useState(() => localStorage.getItem("ledger.timeZone") || "America/New_York");
  const [form, setForm] = useState(() => blankTrade(localStorage.getItem("ledger.timeZone") || "America/New_York"));
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function load() {
    try {
      const [t, a] = await Promise.all([api.journalTrades(source ? { source } : {}), api.journalAnalytics(source)]);
      const items = t.items || [];
      setTrades(items); setAnalytics(a || {});
      if (selectedId && !items.some((x) => x.id === selectedId)) setSelectedId(null);
    } catch (err) { setError(err.message); }
  }
  useEffect(() => { void load(); }, [source]);
  const selected = useMemo(() => trades.find((t) => t.id === selectedId) || null, [trades, selectedId]);
  const derivedQty = Number(form.entry_price) > 0 && Number(form.position_amount) > 0 ? Number(form.position_amount) / Number(form.entry_price) : null;
  const plannedRR = useMemo(() => calcPlannedRR(form), [form.entry_price, form.stop_loss, form.take_profit, form.direction]);

  async function submit(event) {
    event.preventDefault(); setSaving(true); setError("");
    try {
      const numeric = ["entry_price", "exit_price", "position_amount", "stop_loss", "take_profit", "fees", "pnl_override"];
      const payload = { ...form, ticker: form.ticker.toUpperCase(), opened_at: zonedInputToIso(form.opened_at, timeZone), closed_at: zonedInputToIso(form.closed_at, timeZone), quantity: null };
      numeric.forEach((key) => { payload[key] = form[key] === "" ? null : Number(form[key]); });
      const created = await api.createJournalTrade(payload);
      const next = blankTrade(timeZone); next.account = form.account; next.source = form.source;
      setForm(next); setShowForm(false); await load(); setSelectedId(created.id);
    } catch (err) { setError(err.message); }
    finally { setSaving(false); }
  }

  async function remove(id) {
    if (!confirm("Delete this journal trade and its screenshots?")) return;
    await api.deleteJournalTrade(id);
    if (selectedId === id) setSelectedId(null);
    await load();
  }

  return <>
    <div className="rounded-xl border border-stone-200 bg-stone-50 p-3 text-xs text-stone-600">
      <strong>Risk terminology:</strong> Planned R:R is your target distance ÷ stop distance. Realised R is what the trade actually made/lost ÷ initial risk. A planned 2:1 trade closed halfway to target is +1R realised.
    </div>

    <p className="mb-2 mt-5 text-xs font-semibold uppercase tracking-wider text-stone-500">R performance</p>
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
      <Stat label="Trades" value={analytics.trades ?? 0} />
      <Stat label="Win rate" value={analytics.win_rate == null ? "—" : `${analytics.win_rate.toFixed(1)}%`} />
      <Stat label="Avg planned R:R" value={rrValue(analytics.avg_planned_rr)} />
      <Stat label="Average realised R" value={rValue(analytics.avg_r)} />
      <Stat label="Total realised R" value={rValue(analytics.total_r)} />
      <Stat label="Max DD (R)" value={rValue(analytics.max_drawdown_r)} />
      <Stat label="Profit factor (R)" value={analytics.profit_factor_r == null ? "—" : analytics.profit_factor_r === "inf" ? "∞" : Number(analytics.profit_factor_r).toFixed(2)} />
    </div>
    <p className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wider text-stone-500">Execution / money</p>
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Stat label="Net recorded P&L" value={pnlSummary(analytics)} />
      <Stat label="Longest losing streak" value={analytics.longest_losing_streak ?? 0} />
      <Stat label="Average P&L %" value={analytics.avg_pnl_pct == null ? "—" : pct(analytics.avg_pnl_pct)} />
    </div>

    <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-3"><div className="flex items-center gap-2"><span className="text-sm text-stone-500">Source</span><select className="input w-52" value={source} onChange={(e) => setSource(e.target.value)}><option value="">All sources</option>{Object.entries(sourceLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div><div className="flex items-center gap-2"><span className="text-sm text-stone-500">Timezone</span><select className="input w-56" value={timeZone} onChange={(e) => { const zone = e.target.value; setTimeZone(zone); localStorage.setItem("ledger.timeZone", zone); }}>{TIMEZONE_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></div></div>
      <button onClick={() => setShowForm((value) => !value)} className="rounded-md bg-stone-900 px-4 py-2 text-sm text-white">{showForm ? "Close form" : "+ Log trade"}</button>
    </div>
    {error && <p className="mt-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}

    {showForm && <form onSubmit={submit} className="mt-4 rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
      <div><h3 className="font-semibold">Log a manual trade</h3><p className="mt-1 text-xs text-stone-500">Enter actual broker execution prices for day trades. Ticker search is optional: choose a match when available, or keep any symbol/pair you typed. Ledger derives quantity and trade maths.</p></div>
      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
        <Field label="Source"><select className="input" value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })}><option value="live_manual">Live · manual</option><option value="paper_manual">Paper · manual</option></select></Field>
        <Field label="Account"><input className="input" value={form.account} onChange={(e) => setForm({ ...form, account: e.target.value })} /></Field>
        <Field label="Pair / ticker"><SymbolSearch value={form.ticker} onChange={(v) => setForm({ ...form, ticker: v.toUpperCase() })} onSelect={(item) => setForm({ ...form, ticker: item.ticker })} placeholder="AAPL / XAUUSD" /></Field>
        <Field label="Direction"><select className="input" value={form.direction} onChange={(e) => setForm({ ...form, direction: e.target.value })}><option value="long">Long</option><option value="short">Short</option></select></Field>
        <Field label="Input timezone"><select className="input" value={timeZone} onChange={(e) => { const zone = e.target.value; setTimeZone(zone); localStorage.setItem("ledger.timeZone", zone); }}><option value="America/New_York">New York / US market (ET)</option>{TIMEZONE_OPTIONS.filter((x) => x.value !== "America/New_York").map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></Field>
        <Field label="Entry time"><input type="datetime-local" className="input" value={form.opened_at} onChange={(e) => setForm({ ...form, opened_at: e.target.value })} /></Field>
        <Field label="Exit time"><input type="datetime-local" className="input" value={form.closed_at} onChange={(e) => setForm({ ...form, closed_at: e.target.value })} /></Field>
        <Field label="Entry price"><NumberInput value={form.entry_price} set={(v) => setForm({ ...form, entry_price: v })} /></Field>
        <Field label="Stop loss"><NumberInput value={form.stop_loss} set={(v) => setForm({ ...form, stop_loss: v })} /></Field>
        <Field label="Target / take profit"><NumberInput value={form.take_profit} set={(v) => setForm({ ...form, take_profit: v })} /></Field>
        <Field label="Planned R:R"><div className="input flex items-center bg-stone-50 text-stone-600">{rrValue(plannedRR)}</div></Field>
        <Field label="Actual exit price"><NumberInput value={form.exit_price} set={(v) => setForm({ ...form, exit_price: v })} /></Field>
        <Field label="Amount invested / position value"><NumberInput value={form.position_amount} set={(v) => setForm({ ...form, position_amount: v })} /></Field>
        <Field label="Position currency"><input className="input uppercase" maxLength="6" value={form.position_currency} onChange={(e) => setForm({ ...form, position_currency: e.target.value.toUpperCase() })} /></Field>
        <Field label="Calculated quantity"><div className="input flex items-center bg-stone-50 text-stone-600">{derivedQty == null ? "—" : derivedQty.toFixed(8).replace(/0+$/, "").replace(/\.$/, "")}</div></Field>
        <Field label="Fees"><NumberInput value={form.fees} set={(v) => setForm({ ...form, fees: v })} /></Field>
        <Field label="Broker P&L override (optional)"><NumberInput value={form.pnl_override} set={(v) => setForm({ ...form, pnl_override: v })} /></Field>
        <Field label="Override reason"><input className="input" value={form.override_reason} onChange={(e) => setForm({ ...form, override_reason: e.target.value })} placeholder="FX / partial fills / broker fees" /></Field>
        <Field label="Type"><input className="input" value={form.trade_type} onChange={(e) => setForm({ ...form, trade_type: e.target.value })} placeholder="Day / swing" /></Field>
        <Field label="Setup"><input className="input" value={form.setup} onChange={(e) => setForm({ ...form, setup: e.target.value })} placeholder="AMN / First Pullback" /></Field>
        <Field label="Market condition"><input className="input" list="market-conditions" value={form.market_condition} onChange={(e) => setForm({ ...form, market_condition: e.target.value })} /><datalist id="market-conditions"><option>Trending</option><option>Ranging</option><option>Volume</option><option>Countertrend</option><option>Other</option></datalist></Field>
        <Field label="Entry TF"><input className="input" value={form.entry_timeframe} onChange={(e) => setForm({ ...form, entry_timeframe: e.target.value })} placeholder="5m" /></Field>
        <Field label="TF alignment"><input className="input" value={form.timeframe_alignment} onChange={(e) => setForm({ ...form, timeframe_alignment: e.target.value })} /></Field>
        <Field label="DXY"><input className="input" value={form.dxy} onChange={(e) => setForm({ ...form, dxy: e.target.value })} /></Field>
        <Field label="Session"><input className="input" value={form.session_time} onChange={(e) => setForm({ ...form, session_time: e.target.value })} placeholder="London / NY AM" /></Field>
        <Field label="TF Type"><input className="input" value={form.tf_type} onChange={(e) => setForm({ ...form, tf_type: e.target.value })} /></Field>
        <Field label="Wick"><input className="input" value={form.wick} onChange={(e) => setForm({ ...form, wick: e.target.value })} /></Field>
      </div>
      <div className="mt-4 rounded-lg bg-stone-50 p-3 text-xs text-stone-600"><strong>Target</strong> is the planned take-profit. <strong>Exit</strong> is where you actually closed. Planned R:R uses target vs stop; realised R uses actual exit vs initial risk.</div>
      <div className="mt-4 flex justify-end"><button disabled={saving} className="rounded-md bg-stone-900 px-5 py-2 text-sm text-white disabled:opacity-50">{saving ? "Saving…" : "Create trade"}</button></div>
    </form>}

    <section className="mt-5 overflow-hidden rounded-xl border border-stone-200 bg-white shadow-sm">
      <div className="overflow-x-auto"><table className="w-full min-w-[1350px] text-sm"><thead className="bg-stone-50 text-xs uppercase tracking-wide text-stone-500"><tr>{["Time", "Pair", "Source", "Type", "Setup", "Market", "Entry TF", "Planned R:R", "Realised R", "P&L %", "Result", "Account", ""].map((h, i) => <th key={`${h}-${i}`} className="px-3 py-3 text-left">{h}</th>)}</tr></thead><tbody className="divide-y divide-stone-100">{trades.map((t) => <tr key={t.id} className={selectedId === t.id ? "bg-stone-50" : "hover:bg-stone-50"}><td className="whitespace-nowrap px-3 py-3">{formatInZone(t.opened_at, timeZone)}</td><td className="px-3 py-3"><button onClick={() => setSelectedId(t.id)} className="font-mono font-semibold text-blue-700 hover:underline">{t.ticker}</button></td><td className="px-3 py-3 text-stone-500">{sourceLabels[t.source]}</td><td className="px-3 py-3">{t.trade_type || "—"}</td><td className="px-3 py-3">{t.setup || "—"}</td><td className="px-3 py-3">{t.market_condition || "—"}</td><td className="px-3 py-3">{t.entry_timeframe || "—"}</td><td className="px-3 py-3">{rrValue(t.planned_rr)}</td><td className="px-3 py-3">{rValue(t.r_multiple)}</td><td className="px-3 py-3">{pct(t.pnl_pct)}</td><td className={`px-3 py-3 font-medium ${resultTone(t.result)}`}>{t.result?.toUpperCase() || "OPEN"}</td><td className="px-3 py-3">{t.account}</td><td className="px-3 py-3"><button onClick={() => remove(t.id)} className="text-xs text-stone-400 hover:text-red-700">Delete</button></td></tr>)}</tbody></table></div>
      {!trades.length && <p className="p-8 text-center text-sm text-stone-500">No trades logged for this source yet.</p>}
    </section>

    {selected && <TradeDetail trade={selected} timeZone={timeZone} onClose={() => setSelectedId(null)} onChanged={async () => { await load(); }} />}
  </>;
}

function calcPlannedRR(t) {
  const entry = Number(t.entry_price), stop = Number(t.stop_loss), target = Number(t.take_profit);
  if (![entry, stop, target].every(Number.isFinite) || entry === stop) return null;
  if (t.direction === "long") return stop < entry && target > entry ? (target - entry) / (entry - stop) : null;
  return stop > entry && target < entry ? (entry - target) / (stop - entry) : null;
}
function NumberInput({ value, set }) { return <input type="number" step="any" className="input" value={value} onChange={(e) => set(e.target.value)} />; }
function Field({ label, children }) { return <label className="block"><span className="mb-1 block text-xs font-medium text-stone-500">{label}</span>{children}</label>; }
function Stat({ label, value }) { return <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm"><p className="text-xs uppercase tracking-wide text-stone-500">{label}</p><p className="mt-2 text-xl font-semibold">{value}</p></div>; }
