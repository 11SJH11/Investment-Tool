import { useEffect, useState } from "react";
import { api } from "../../api/client";
import BrokerPortfolioPanel from "./BrokerPortfolioPanel";
import SymbolSearch from "../../components/SymbolSearch";
import { TIMEZONE_OPTIONS, nowInZoneInput, zonedInputToIso } from "../../utils/timezones";

function money(v, currency = "USD") { return v == null ? "—" : Intl.NumberFormat("en-GB", { style: "currency", currency, maximumFractionDigits: 2 }).format(v); }
function pct(v) { return v == null ? "—" : `${Number(v).toFixed(2)}%`; }
function blankForm(zone = "America/New_York") { return { account: "Main", ticker: "", action: "BUY", occurred_at: nowInZoneInput(zone), input_mode: "amount", amount: "", quantity: "", price_override: "", fees: "0", base_currency: "GBP", asset_currency: "USD", note: "" }; }

export default function PortfolioPage({ onOpenTicker }) {
  const [data, setData] = useState({ holdings: [], transactions: [], accounts: [], base_currency: "GBP" });
  const [account, setAccount] = useState("");
  const [timeZone, setTimeZone] = useState(() => localStorage.getItem("ledger.timeZone") || "America/New_York");
  const [form, setForm] = useState(() => blankForm(localStorage.getItem("ledger.timeZone") || "America/New_York"));
  const [tickerSearch, setTickerSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);

  const load = async (refresh = false) => {
    setLoading(true); setError("");
    try { setData(refresh ? await api.refreshPortfolioPrices(account) : await api.portfolio(account)); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [account]);

  const submit = async (e) => {
    e.preventDefault(); setSaving(true); setError("");
    try {
      const mode = form.input_mode;
      await api.addPortfolioTransaction({
        account: form.account,
        ticker: form.ticker.toUpperCase(),
        action: form.action,
        occurred_at: zonedInputToIso(form.occurred_at, timeZone),
        input_mode: mode,
        amount: mode === "amount" ? Number(form.amount) : null,
        quantity: mode === "quantity" ? Number(form.quantity) : null,
        price_override: form.price_override === "" ? null : Number(form.price_override),
        fees: Number(form.fees || 0),
        base_currency: form.base_currency,
        asset_currency: form.asset_currency,
        fees_currency: form.base_currency,
        note: form.note,
      });
      const next = blankForm(timeZone); next.account = form.account; setForm(next); setTickerSearch(""); setShowForm(false); await load();
    } catch (e2) { setError(e2.message); }
    finally { setSaving(false); }
  };

  const remove = async (id) => {
    if (!confirm("Delete this portfolio transaction?")) return;
    try { await api.deletePortfolioTransaction(id); await load(); }
    catch (e) { setError(e.message); }
  };

  const base = data.base_currency || "GBP";
  const useBase = data.base_currency_complete && data.base_market_value != null;

  return (
    <div className="max-w-[1450px]">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="text-xs uppercase tracking-widest text-stone-500">Long-term investing</p><h2 className="mt-1 text-3xl font-semibold">Investment Portfolio</h2><p className="mt-2 text-sm text-stone-600">Enter what you invested; Ledger can estimate the historical share price and calculate fractional quantity. Exact broker fills can always be overridden.</p></div>
        <div className="flex gap-2">
          <select value={account} onChange={(e) => setAccount(e.target.value)} className="input w-44"><option value="">All accounts</option>{(data.accounts || []).map((a) => <option key={a}>{a}</option>)}</select>
          <button onClick={() => load(true)} className="rounded-md border border-stone-300 bg-white px-3 py-2 text-sm">Refresh prices</button>
          <button onClick={() => setShowForm((v) => !v)} className="rounded-md bg-stone-900 px-4 py-2 text-sm text-white">{showForm ? "Close" : "+ Transaction"}</button>
        </div>
      </div>

      <BrokerPortfolioPanel/>
      {error && <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}

      {showForm && <form onSubmit={submit} className="mt-5 rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
        <div><h3 className="font-semibold">Add buy / sell</h3><p className="mt-1 text-xs text-stone-500">Leave actual price blank to use the closest Alpaca 1-minute close as an estimate. For a precise broker record, enter your actual fill.</p></div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Account"><input className="input" value={form.account} onChange={(e) => setForm({ ...form, account: e.target.value })} /></Field>
          <Field label="Ticker"><SymbolSearch value={tickerSearch} onChange={(v) => { setTickerSearch(v); setForm({ ...form, ticker: v.toUpperCase() }); }} onSelect={(item) => { setTickerSearch(item.ticker); setForm({ ...form, ticker: item.ticker }); }} /></Field>
          <Field label="Action"><select className="input" value={form.action} onChange={(e) => setForm({ ...form, action: e.target.value })}><option>BUY</option><option>SELL</option></select></Field>
          <Field label="Date / time"><input type="datetime-local" className="input" value={form.occurred_at} onChange={(e) => setForm({ ...form, occurred_at: e.target.value })} /></Field>
          <Field label="Input timezone"><select className="input" value={timeZone} onChange={(e) => { const zone = e.target.value; setTimeZone(zone); localStorage.setItem("ledger.timeZone", zone); }}>{TIMEZONE_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></Field>

          <Field label="Enter by"><select className="input" value={form.input_mode} onChange={(e) => setForm({ ...form, input_mode: e.target.value })}><option value="amount">{form.action === "BUY" ? "Amount invested" : "Amount to sell"}</option><option value="quantity">Number of shares</option></select></Field>
          {form.input_mode === "amount" ?
            <Field label={`${form.action === "BUY" ? "Amount invested" : "Amount to sell"} (${form.base_currency})`}><input required min="0" step="any" type="number" className="input" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></Field> :
            <Field label="Number of shares"><input required min="0" step="any" type="number" className="input" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></Field>}
          <Field label="Actual fill price (optional, USD)"><input min="0" step="any" type="number" className="input" value={form.price_override} onChange={(e) => setForm({ ...form, price_override: e.target.value })} placeholder="Auto-fetch if blank" /></Field>
          <Field label={`Fees (${form.base_currency})`}><input min="0" step="any" type="number" className="input" value={form.fees} onChange={(e) => setForm({ ...form, fees: e.target.value })} /></Field>
          <Field label="Base currency"><select className="input" value={form.base_currency} onChange={(e) => setForm({ ...form, base_currency: e.target.value })}><option>GBP</option><option>USD</option></select></Field>
          <Field label="Note"><input className="input" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="Why / broker note" /></Field>
        </div>
        <div className="mt-4 flex justify-end"><button disabled={saving || !form.ticker} className="rounded-md bg-stone-900 px-5 py-2 text-sm text-white disabled:opacity-50">{saving ? "Resolving price / saving…" : "Save transaction"}</button></div>
      </form>}

      {!useBase && (data.transactions || []).length > 0 && <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">Some older transactions do not contain historical FX/base-currency data, so Ledger cannot present a fully consistent GBP portfolio total for them. New amount-based transactions store this automatically.</div>}

      <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
        <Stat label={`Market value (${useBase ? base : "USD"})`} value={money(useBase ? data.base_market_value : data.market_value, useBase ? base : "USD")} />
        <Stat label={`Open cost basis (${useBase ? base : "USD"})`} value={money(useBase ? data.base_open_cost_basis : data.open_cost_basis, useBase ? base : "USD")} />
        <Stat label="Unrealised P&L" value={money(useBase ? data.base_unrealized_pnl : data.unrealized_pnl, useBase ? base : "USD")} tone={Number(useBase ? data.base_unrealized_pnl : data.unrealized_pnl) >= 0 ? "good" : "bad"} />
        <Stat label="Unrealised return" value={pct(useBase ? data.base_unrealized_return_pct : data.unrealized_return_pct)} tone={Number(useBase ? data.base_unrealized_pnl : data.unrealized_pnl) >= 0 ? "good" : "bad"} />
        <Stat label="Realised P&L" value={money(useBase ? data.base_realized_pnl : data.realized_pnl, useBase ? base : "USD")} />
        <Stat label="Largest position" value={pct(data.largest_position_pct)} />
      </div>
      {data.fx_rate && <p className="mt-2 text-xs text-stone-500">Portfolio conversion: 1 {base} = {Number(data.fx_rate).toFixed(4)} USD · {data.fx_source || "FX"} · {data.fx_date || "latest"}</p>}

      <section className="mt-6 overflow-hidden rounded-xl border border-stone-200 bg-white shadow-sm">
        <div className="border-b border-stone-100 px-5 py-4"><h3 className="font-semibold">Current holdings</h3></div>
        <div className="overflow-x-auto"><table className="w-full min-w-[1050px] text-sm"><thead className="bg-stone-50 text-xs uppercase tracking-wide text-stone-500"><tr>{["Ticker","Shares owned","Average buy price (USD)","Current share price (USD)",`Current value (${useBase ? base : "USD"})`,"Unrealised P&L","Return","Allocation","Realised P&L"].map((x) => <th key={x} className="px-4 py-3 text-left">{x}</th>)}</tr></thead><tbody className="divide-y divide-stone-100">{(data.holdings || []).map((h) => <tr key={h.ticker}><td className="px-4 py-3"><button className="font-mono font-semibold text-blue-700 hover:underline" onClick={() => onOpenTicker?.(h.ticker)}>{h.ticker}</button></td><td className="px-4 py-3 tabular-nums">{h.quantity}</td><td className="px-4 py-3">{money(h.average_cost, "USD")}</td><td className="px-4 py-3">{money(h.current_price, "USD")}</td><td className="px-4 py-3">{money(useBase ? h.base_market_value : h.market_value, useBase ? base : "USD")}</td><td className={`px-4 py-3 ${Number(useBase ? h.base_unrealized_pnl : h.unrealized_pnl) >= 0 ? "text-emerald-700" : "text-red-700"}`}>{money(useBase ? h.base_unrealized_pnl : h.unrealized_pnl, useBase ? base : "USD")}</td><td className="px-4 py-3">{pct(useBase ? h.base_unrealized_return_pct : h.unrealized_return_pct)}</td><td className="px-4 py-3">{pct(h.allocation_pct)}</td><td className="px-4 py-3">{money(useBase ? h.base_realized_pnl : h.realized_pnl, useBase ? base : "USD")}</td></tr>)}</tbody></table></div>
        {!loading && !(data.holdings || []).length && <p className="p-8 text-center text-sm text-stone-500">No holdings yet. Add your first buy transaction above.</p>}
      </section>

      <section className="mt-6 overflow-hidden rounded-xl border border-stone-200 bg-white shadow-sm">
        <div className="border-b border-stone-100 px-5 py-4"><h3 className="font-semibold">Transaction history</h3></div>
        <div className="overflow-x-auto"><table className="w-full min-w-[1100px] text-sm"><thead className="bg-stone-50 text-xs uppercase tracking-wide text-stone-500"><tr>{["Date","Account","Ticker","Action","Amount / input","Shares bought / sold","Transaction share price","Price source","Fees","Note",""] .map((x, i) => <th key={`${x}-${i}`} className="px-4 py-3 text-left">{x}</th>)}</tr></thead><tbody className="divide-y divide-stone-100">{(data.transactions || []).map((t) => <tr key={t.id}><td className="px-4 py-3 whitespace-nowrap">{new Date(t.occurred_at).toLocaleString("en-GB")}</td><td className="px-4 py-3">{t.account}</td><td className="px-4 py-3 font-mono">{t.ticker}</td><td className={`px-4 py-3 font-medium ${t.action === "BUY" ? "text-emerald-700" : "text-red-700"}`}>{t.action}</td><td className="px-4 py-3">{t.input_mode === "amount" && t.input_amount != null ? money(t.input_amount, t.base_currency || "GBP") : "Entered as shares"}</td><td className="px-4 py-3">{Number(t.quantity).toFixed(8)}</td><td className="px-4 py-3">{money(t.price, t.asset_currency || "USD")}</td><td className="px-4 py-3 text-xs text-stone-500">{t.price_overridden ? "Manual fill" : (t.price_source || "Legacy")}</td><td className="px-4 py-3">{money(t.fees, t.fees_currency || t.base_currency || "GBP")}</td><td className="px-4 py-3 max-w-xs truncate">{t.note || "—"}</td><td className="px-4 py-3"><button onClick={() => remove(t.id)} className="text-xs text-stone-400 hover:text-red-700">Delete</button></td></tr>)}</tbody></table></div>
      </section>
    </div>
  );
}

function Stat({ label, value, tone }) { return <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm"><p className="text-xs uppercase tracking-wide text-stone-500">{label}</p><p className={`mt-2 text-xl font-semibold ${tone === "good" ? "text-emerald-700" : tone === "bad" ? "text-red-700" : ""}`}>{value}</p></div>; }
function Field({ label, children }) { return <label className="block"><span className="mb-1 block text-xs font-medium text-stone-500">{label}</span>{children}</label>; }
