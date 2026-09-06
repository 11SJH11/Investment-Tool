import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import WatchlistBar from "../../components/WatchlistBar";
import { useWatchlist } from "../../app/watchlist";

const initialFilters = {
  query: "", exchange: "", security_type: "stock", tradable: true, fractionable: "", shortable: "",
  min_price: "", max_price: "", min_market_cap: "", max_market_cap: "",
  min_pe: "", max_pe: "", min_revenue_growth: "", min_net_margin: "",
  min_operating_margin: "", min_roe: "", positive_fcf: "", require_fundamentals: false,
};

function percentToDecimal(value) { return value === "" ? "" : Number(value) / 100; }
function billions(value) { return value === "" ? "" : Number(value) * 1_000_000_000; }
function money(value) {
  if (value == null) return "—";
  return Intl.NumberFormat("en-GB", { notation: "compact", maximumFractionDigits: 2, style: "currency", currency: "USD" }).format(value);
}
function pct(value) { return value == null ? "—" : `${(value * 100).toFixed(1)}%`; }
function num(value, digits = 2) { return value == null ? "—" : Number(value).toFixed(digits); }
function shortStamp(value) {
  if (!value) return "not refreshed";
  const raw = String(value);
  const date = new Date(raw.endsWith("Z") || raw.includes("+") ? raw : `${raw}Z`);
  return Number.isNaN(date.getTime()) ? raw : new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

const columns = [
  ["favorite", "★"], ["ticker", "Ticker"], ["name", "Company"], ["security_type", "Type"], ["exchange", "Exchange"], ["price", "Price"],
  ["market_cap", "Market cap"], ["pe_ratio", "P/E (FY)"], ["revenue_growth_yoy", "Revenue growth"],
  ["net_margin", "Net margin"], ["return_on_equity", "ROE"], ["free_cash_flow", "FCF"],
];

export default function ScreenerPage({ onOpenTicker }) {
  const watchlist = useWatchlist();
  const [filters, setFilters] = useState(initialFilters);
  const [result, setResult] = useState({ total: 0, items: [], coverage: {} });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [sortBy, setSortBy] = useState("ticker");
  const [sortDir, setSortDir] = useState("asc");
  const [offset, setOffset] = useState(0);
  const limit = 100;

  const params = useMemo(() => ({
    ...filters,
    min_market_cap: billions(filters.min_market_cap), max_market_cap: billions(filters.max_market_cap),
    min_revenue_growth: percentToDecimal(filters.min_revenue_growth), min_net_margin: percentToDecimal(filters.min_net_margin),
    min_operating_margin: percentToDecimal(filters.min_operating_margin), min_roe: percentToDecimal(filters.min_roe),
    positive_fcf: filters.positive_fcf === "" ? "" : filters.positive_fcf === "true",
    fractionable: filters.fractionable === "" ? "" : filters.fractionable === "true",
    shortable: filters.shortable === "" ? "" : filters.shortable === "true",
    sort_by: sortBy, sort_dir: sortDir, limit, offset,
  }), [filters, sortBy, sortDir, offset]);

  const run = async () => {
    setLoading(true); setError("");
    try { setResult(await api.screen(params)); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  useEffect(() => { run(); }, [sortBy, sortDir, offset]);

  const update = (key, value) => { setFilters((current) => ({ ...current, [key]: value })); setOffset(0); };
  const sort = (key) => {
    if (sortBy === key) setSortDir((d) => d === "asc" ? "desc" : "asc");
    else { setSortBy(key); setSortDir("desc"); }
  };

  const refresh = async (kind) => {
    setMessage(""); setError(""); setLoading(true);
    try {
      if (kind === "prices") {
        const r = await api.refreshScreenerPrices();
        setMessage(`Price snapshot refreshed: ${r.stored.toLocaleString()} securities stored from ${r.feed}.`);
      } else {
        const r = await api.refreshScreenerFundamentals();
        setMessage(`SEC fundamentals refreshed for ${r.ticker_records.toLocaleString()} ticker records.`);
      }
      await run();
    } catch (e) { setError(e.message); setLoading(false); }
  };

  return (
    <div className="max-w-[1500px]">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="text-xs uppercase tracking-widest text-stone-500">Market scanner</p><h2 className="mt-1 text-3xl font-semibold">Screener</h2><p className="mt-2 text-sm text-stone-600">Filter the local US security universe. Stocks are shown by default; ETFs, SPACs, warrants and other instruments can be selected explicitly.</p></div>
        <div className="flex gap-2"><button onClick={() => refresh("prices")} className="rounded-md border border-stone-300 bg-white px-3 py-2 text-sm hover:bg-stone-50">Refresh prices</button><button onClick={() => refresh("fundamentals")} className="rounded-md bg-stone-900 px-3 py-2 text-sm text-white">Refresh SEC fundamentals</button></div>
      </div>

      {error && <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
      {message && <div className="mt-4 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{message}</div>}

      <section className="mt-5 rounded-xl border border-stone-200 bg-white p-4 shadow-sm"><div className="mb-2 flex items-center justify-between"><div><h3 className="font-semibold">Watchlist</h3><p className="text-xs text-stone-500">Favourite symbols stay one click away before you start filtering.</p></div></div><WatchlistBar onSelect={onOpenTicker} compact title="" /></section>

      <section className="mt-5 rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
          <Field label="Ticker / company"><input value={filters.query} onChange={(e) => update("query", e.target.value)} placeholder="AAPL" className="input" /></Field>
          <Field label="Instrument"><select value={filters.security_type} onChange={(e) => update("security_type", e.target.value)} className="input"><option value="stock">Stocks (default)</option><option value="common_stock">Common stocks only</option><option value="adr">ADRs</option><option value="reit">REITs</option><option value="etf">ETFs</option><option value="etn">ETNs</option><option value="spac">SPACs</option><option value="preferred">Preferred</option><option value="unit">Units</option><option value="warrant">Warrants</option><option value="right">Rights</option><option value="fund">Funds</option><option value="all">All instruments</option></select></Field>
          <Field label="Exchange"><select value={filters.exchange} onChange={(e) => update("exchange", e.target.value)} className="input"><option value="">All</option><option>NASDAQ</option><option>NYSE</option><option>ARCA</option><option>AMEX</option></select></Field>
          <Field label="Price min ($)"><input type="number" value={filters.min_price} onChange={(e) => update("min_price", e.target.value)} className="input" /></Field>
          <Field label="Price max ($)"><input type="number" value={filters.max_price} onChange={(e) => update("max_price", e.target.value)} className="input" /></Field>
          <Field label="Market cap min ($bn)"><input type="number" value={filters.min_market_cap} onChange={(e) => update("min_market_cap", e.target.value)} className="input" /></Field>
          <Field label="Market cap max ($bn)"><input type="number" value={filters.max_market_cap} onChange={(e) => update("max_market_cap", e.target.value)} className="input" /></Field>
          <Field label="P/E min"><input type="number" value={filters.min_pe} onChange={(e) => update("min_pe", e.target.value)} className="input" /></Field>
          <Field label="P/E max"><input type="number" value={filters.max_pe} onChange={(e) => update("max_pe", e.target.value)} className="input" /></Field>
          <Field label="Revenue growth min (%)"><input type="number" value={filters.min_revenue_growth} onChange={(e) => update("min_revenue_growth", e.target.value)} className="input" /></Field>
          <Field label="Net margin min (%)"><input type="number" value={filters.min_net_margin} onChange={(e) => update("min_net_margin", e.target.value)} className="input" /></Field>
          <Field label="ROE min (%)"><input type="number" value={filters.min_roe} onChange={(e) => update("min_roe", e.target.value)} className="input" /></Field>
          <Field label="Free cash flow"><select value={filters.positive_fcf} onChange={(e) => update("positive_fcf", e.target.value)} className="input"><option value="">Any</option><option value="true">Positive</option><option value="false">Zero / negative</option></select></Field>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-4 border-t border-stone-100 pt-4 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" checked={filters.require_fundamentals} onChange={(e) => update("require_fundamentals", e.target.checked)} />Has SEC fundamentals</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={filters.tradable} onChange={(e) => update("tradable", e.target.checked)} />Tradable</label>
          <button onClick={() => { setFilters(initialFilters); setOffset(0); }} className="text-stone-500 hover:text-stone-900">Reset</button>
          <button onClick={run} disabled={loading} className="ml-auto rounded-md bg-stone-900 px-5 py-2 text-white disabled:opacity-50">{loading ? "Scanning…" : "Run screener"}</button>
        </div>
      </section>

      {Number(result.coverage?.fundamentals || 0) === 0 && <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">Fundamental columns will stay empty until you run <strong>Refresh SEC fundamentals</strong>. Screener scans remain local after that bulk refresh.</div>}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-stone-600">
        <span>{result.total.toLocaleString()} matches · fundamentals {Number(result.coverage?.fundamentals || 0).toLocaleString()} ({shortStamp(result.coverage?.fundamentals_updated_at)}) · prices {Number(result.coverage?.prices || 0).toLocaleString()} ({shortStamp(result.coverage?.price_data_timestamp || result.coverage?.prices_updated_at)})</span>
        <span>Rows {result.total ? offset + 1 : 0}–{Math.min(offset + limit, result.total)}</span>
      </div>

      <section className="mt-3 overflow-hidden rounded-xl border border-stone-200 bg-white shadow-sm">
        <div className="overflow-x-auto"><table className="w-full min-w-[1100px] text-sm"><thead className="bg-stone-50 text-xs uppercase tracking-wide text-stone-500"><tr>{columns.map(([key, label]) => <th key={key} className="px-3 py-3 text-left">{key === "favorite" ? label : <button onClick={() => sort(key)} className="whitespace-nowrap hover:text-stone-900">{label}{sortBy === key ? (sortDir === "asc" ? " ↑" : " ↓") : ""}</button>}</th>)}</tr></thead><tbody className="divide-y divide-stone-100">{result.items.map((row) => <tr key={row.ticker} className="hover:bg-stone-50"><td className="px-3 py-3"><button className={`favorite-btn ${watchlist.has(row.ticker)?"active":""}`} title={watchlist.has(row.ticker)?"Remove from watchlist":"Add to watchlist"} onClick={()=>watchlist.toggle(row.ticker)}>★</button></td><td className="px-3 py-3"><button onClick={() => onOpenTicker(row.ticker)} className="font-mono font-semibold text-blue-700 hover:underline">{row.ticker}</button></td><td className="max-w-xs truncate px-3 py-3">{row.name}</td><td className="px-3 py-3 text-stone-500">{typeLabel(row.security_type)}</td><td className="px-3 py-3 text-stone-500">{row.exchange || "—"}</td><td className="px-3 py-3 tabular-nums">{row.price == null ? "—" : `$${num(row.price)}`}</td><td className="px-3 py-3 tabular-nums">{money(row.market_cap)}</td><td className="px-3 py-3 tabular-nums">{num(row.pe_ratio)}</td><td className="px-3 py-3 tabular-nums">{pct(row.revenue_growth_yoy)}</td><td className="px-3 py-3 tabular-nums">{pct(row.net_margin)}</td><td className="px-3 py-3 tabular-nums">{pct(row.return_on_equity)}</td><td className="px-3 py-3 tabular-nums">{money(row.free_cash_flow)}</td></tr>)}</tbody></table></div>
        {result.items.length === 0 && <p className="p-8 text-center text-sm text-stone-500">No securities match these filters. If fundamental/price filters are set, make sure the corresponding snapshots have been refreshed.</p>}
        <div className="flex justify-end gap-2 border-t border-stone-100 p-3"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))} className="rounded border px-3 py-1.5 disabled:opacity-40">Previous</button><button disabled={offset + limit >= result.total} onClick={() => setOffset(offset + limit)} className="rounded border px-3 py-1.5 disabled:opacity-40">Next</button></div>
      </section>
    </div>
  );
}

function typeLabel(value) { return ({ common_stock: "Stock", adr: "ADR", reit: "REIT", etf: "ETF", etn: "ETN", spac: "SPAC", preferred: "Preferred", unit: "Unit", warrant: "Warrant", right: "Right", fund: "Fund", other: "Other" })[value] || value || "—"; }

function Field({ label, children }) { return <label className="block"><span className="mb-1 block text-xs font-medium text-stone-500">{label}</span>{children}</label>; }
