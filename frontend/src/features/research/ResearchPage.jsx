import { useEffect, useState } from "react";
import { api } from "../../api/client";
import SymbolSearch from "../../components/SymbolSearch";
import PriceChart from "./PriceChart";
import { TIMEZONE_OPTIONS } from "../../utils/timezones";

const timeframeOptions = [
  ["1m", 5], ["5m", 30], ["15m", 90], ["30m", 180], ["1h", 365], ["4h", 730], ["1d", 1825], ["1w", 3650],
];
const typeLabels = {
  common_stock: "Common stock", adr: "ADR", reit: "REIT", etf: "ETF", etn: "ETN",
  spac: "SPAC", preferred: "Preferred", unit: "Unit", warrant: "Warrant", right: "Right", fund: "Fund", other: "Other",
};
function money(v) { return v == null ? "—" : Intl.NumberFormat("en-GB", { style: "currency", currency: "USD", notation: Math.abs(v) >= 1e6 ? "compact" : "standard", maximumFractionDigits: 2 }).format(v); }
function pct(v) { return v == null ? "—" : `${(Number(v) * 100).toFixed(1)}%`; }
function num(v) { return v == null ? "—" : Number(v).toFixed(2); }
function sourceLabel(source) { return source ? source.replace("alpaca-", "Alpaca ").replace("sec", "SEC").toUpperCase() : "—"; }
function formatStamp(value) {
  if (!value) return "Not cached";
  const date = new Date(value.endsWith?.("Z") || value.includes("+") ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export default function ResearchPage({ selectedTicker = "AAPL", onTickerChange }) {
  const [search, setSearch] = useState(selectedTicker);
  const [ticker, setTicker] = useState(selectedTicker);
  const [profile, setProfile] = useState(null);
  const [bars, setBars] = useState([]);
  const [barMeta, setBarMeta] = useState({});
  const [overlays, setOverlays] = useState([]);
  const [overlayConfig, setOverlayConfig] = useState({ ema: 20, sma: 50, vwap: null });
  const [overlayEnabled, setOverlayEnabled] = useState({ ema: false, sma: false, vwap: false });
  const [timeframe, setTimeframe] = useState("1d");
  const [session, setSession] = useState(() => localStorage.getItem("ledger.chartSession") || "regular");
  const [timeZone, setTimeZone] = useState(() => localStorage.getItem("ledger.timeZone") || "America/New_York");
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState("");
  const [profileLoading, setProfileLoading] = useState(false);
  const [barsLoading, setBarsLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    if (selectedTicker && selectedTicker !== ticker) {
      setTicker(selectedTicker);
      setSearch(selectedTicker);
    }
  }, [selectedTicker]);

  const loadProfile = async (refresh = false) => {
    if (!ticker) return;
    setProfileLoading(true);
    setError("");
    if (!refresh) setProfile(null);
    try { setProfile(await api.research(ticker, refresh)); }
    catch (e) { setError(e.message); }
    finally { setProfileLoading(false); }
  };

  const loadBars = async (refresh = false) => {
    if (!ticker) return;
    const lookback = timeframeOptions.find(([tf]) => tf === timeframe)?.[1] || 365;
    setBarsLoading(true);
    try {
      const result = await api.researchBars(ticker, timeframe, lookback, refresh, session);
      setBars(result.bars || []);
      setBarMeta(result || {});
    } catch (e) {
      setError(e.message);
      setBars([]);
    } finally {
      setBarsLoading(false);
    }
  };

  const loadOverlays = async () => {
    if (!ticker) return;
    const active = Object.entries(overlayConfig).filter(([key]) => overlayEnabled[key]);
    if (!active.length) { setOverlays([]); return; }
    const lookback = timeframeOptions.find(([tf]) => tf === timeframe)?.[1] || 365;
    try {
      const results = await Promise.all(active.map(async ([key, value]) => {
        const length = key === "vwap" ? null : Number(value);
        const response = await api.researchIndicator(ticker, key, timeframe, lookback, session, length);
        return { key, label: key === "vwap" ? "VWAP" : `${key.toUpperCase()} ${length}`, values: response.values || [] };
      }));
      setOverlays(results);
    } catch (e) { setError(e.message); setOverlays([]); }
  };

  useEffect(() => { if (ticker) { loadProfile(); loadBars(); } }, [ticker]);
  useEffect(() => { if (ticker) loadBars(); }, [timeframe, session]);
  useEffect(() => { if (ticker && bars.length) loadOverlays(); }, [ticker, timeframe, session, JSON.stringify(overlayConfig), JSON.stringify(overlayEnabled), bars.length]);
  useEffect(() => { localStorage.setItem("ledger.chartSession", session); }, [session]);
  useEffect(() => { localStorage.setItem("ledger.timeZone", timeZone); }, [timeZone]);
  useEffect(() => {
    if (!expanded) return;
    const onKey = (event) => { if (event.key === "Escape") setExpanded(false); };
    document.addEventListener("keydown", onKey);
    const old = document.body.style.overflow; document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = old; };
  }, [expanded]);

  const choose = (item) => {
    setTicker(item.ticker);
    setSearch(item.ticker);
    onTickerChange?.(item.ticker);
  };

  const refreshAll = async () => {
    setRefreshing(true);
    try { await Promise.all([loadProfile(true), loadBars(true)]); }
    finally { setRefreshing(false); }
  };

  const metrics = profile?.metrics || {};
  const symbol = profile?.symbol;
  const fundamentalAvailability = profile?.availability?.fundamentals;
  const hasFundamentals = Boolean(metrics.has_fundamentals);

  return (
    <div className="max-w-[1450px]">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div>
          <div className="max-w-xl"><SymbolSearch value={search} onChange={setSearch} onSelect={choose} /><p className="mt-2 text-xs text-stone-500">Searches your locally cached security universe. Type an exact ticker and press Enter to open it.</p></div>
          {error && <div className="mt-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
          {profileLoading && !symbol && <div className="mt-6 rounded-xl border border-stone-200 bg-white p-5 text-sm text-stone-500 shadow-sm">Loading company data, SEC fundamentals and latest price…</div>}
          {symbol && <div className="mt-6 flex flex-wrap items-end justify-between gap-4"><div><p className="font-mono text-sm text-stone-500">{symbol.ticker} · {symbol.exchange || "US"} · {typeLabels[symbol.security_type] || symbol.security_type || "Security"}</p><h2 className="text-3xl font-semibold">{symbol.name}</h2></div><div className="text-right"><div className="text-3xl font-semibold tabular-nums">{metrics.price == null ? "—" : `$${num(metrics.price)}`}</div><p className="text-xs text-stone-500">{metrics.price == null ? "Price unavailable" : `${sourceLabel(metrics.price_source)} · ${formatStamp(metrics.price_timestamp)}`}</p></div></div>}
        </div>
        <div className="flex items-end justify-end"><button onClick={refreshAll} disabled={refreshing || profileLoading || barsLoading} className="rounded-md border border-stone-300 bg-white px-3 py-2 text-sm disabled:opacity-50">{refreshing ? "Refreshing…" : "Refresh"}</button></div>
      </div>

      <section className={`${expanded ? "fixed inset-3 z-50 mt-0" : "mt-6"} overflow-hidden rounded-xl border border-stone-200 bg-white shadow-xl`}>
        <div className="flex flex-wrap items-center gap-1 border-b border-stone-200 p-3">
          {timeframeOptions.map(([tf]) => <button key={tf} onClick={() => setTimeframe(tf)} className={`rounded px-3 py-1.5 text-sm ${timeframe === tf ? "bg-stone-900 text-white" : "hover:bg-stone-100"}`}>{tf}</button>)}
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-1 text-xs text-stone-500">Session<select className="input w-auto py-1 text-xs" value={session} onChange={(e) => setSession(e.target.value)}><option value="regular">Regular 09:30–16:00 ET</option><option value="extended">Extended 04:00–20:00 ET</option></select></label>
            <label className="flex items-center gap-1 text-xs text-stone-500">Timezone<select className="input w-auto py-1 text-xs" value={timeZone} onChange={(e) => setTimeZone(e.target.value)}>{TIMEZONE_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
            <label className="flex items-center gap-1 text-xs text-stone-500"><input type="checkbox" checked={overlayEnabled.ema} onChange={(e) => setOverlayEnabled({ ...overlayEnabled, ema: e.target.checked })} />EMA<input className="input w-16 py-1 text-xs" type="number" min="1" value={overlayConfig.ema} onChange={(e) => setOverlayConfig({ ...overlayConfig, ema: e.target.value || 20 })} /></label>
            <label className="flex items-center gap-1 text-xs text-stone-500"><input type="checkbox" checked={overlayEnabled.sma} onChange={(e) => setOverlayEnabled({ ...overlayEnabled, sma: e.target.checked })} />SMA<input className="input w-16 py-1 text-xs" type="number" min="1" value={overlayConfig.sma} onChange={(e) => setOverlayConfig({ ...overlayConfig, sma: e.target.value || 50 })} /></label>
            <label className="flex items-center gap-1 text-xs text-stone-500"><input type="checkbox" checked={overlayEnabled.vwap} onChange={(e) => setOverlayEnabled({ ...overlayEnabled, vwap: e.target.checked })} />VWAP</label>
            <button type="button" onClick={() => setExpanded((v) => !v)} className="rounded-md border border-stone-300 bg-white px-3 py-1.5 text-xs">{expanded ? "Close expanded" : "Expand chart"}</button>
          </div>
        </div>
        {barsLoading ? <div className={`flex ${expanded ? "h-[calc(100vh-145px)]" : "h-[520px]"} items-center justify-center bg-neutral-950 text-sm text-neutral-400`}>Loading {timeframe} chart data…</div> : bars.length ? <PriceChart bars={bars} overlays={overlays} timeZone={timeZone} expanded={expanded} /> : <div className={`flex ${expanded ? "h-[calc(100vh-145px)]" : "h-[520px]"} items-center justify-center bg-neutral-950 text-sm text-neutral-400`}>No chart data loaded.</div>}
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-stone-200 px-4 py-2 text-[11px] text-stone-500">
          <span>Data: Alpaca {String(barMeta.feed || "configured").toUpperCase()} · {barMeta.historical_delay_minutes ? `~${barMeta.historical_delay_minutes} min delayed` : "plan-dependent"} · {barMeta.session === "regular" ? "regular session" : "extended session"}{barMeta.aggregation === "session_aligned_from_30m" ? " · session-aligned from 30m bars" : ""} · adjustment: {barMeta.adjustment || "—"}</span>
          <span>Indicators: shared Ledger backend calculations · Charts powered by <a className="underline" href="https://www.tradingview.com/" target="_blank" rel="noreferrer">TradingView Lightweight Charts™</a></span>
        </div>
      </section>

      {profileLoading && symbol && <div className="mt-6 rounded-xl border border-stone-200 bg-white p-5 text-sm text-stone-500 shadow-sm">Refreshing company data…</div>}

      {!profileLoading && symbol && hasFundamentals && (
        <section className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Market cap" value={money(metrics.market_cap)} />
          <Metric label="P/E (FY EPS)" value={num(metrics.pe_ratio)} />
          <Metric label="Revenue" value={money(metrics.revenue)} />
          <Metric label="Revenue growth" value={pct(metrics.revenue_growth_yoy)} />
          <Metric label="Net margin" value={pct(metrics.net_margin)} />
          <Metric label="Operating margin" value={pct(metrics.operating_margin)} />
          <Metric label="ROE" value={pct(metrics.return_on_equity)} />
          <Metric label="Free cash flow" value={money(metrics.free_cash_flow)} />
          <Metric label="EPS diluted" value={metrics.eps_diluted == null ? "—" : `$${num(metrics.eps_diluted)}`} />
          <Metric label="Cash" value={money(metrics.cash)} />
          <Metric label="Assets" value={money(metrics.assets)} />
          <Metric label="Liabilities" value={money(metrics.liabilities)} />
        </section>
      )}

      {!profileLoading && symbol && !hasFundamentals && (
        <section className="mt-6 rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
          <h3 className="font-semibold">Fundamentals unavailable</h3>
          <p className="mt-2 text-sm text-stone-600">{fundamentalAvailability?.message || "Ledger could not find usable SEC company fundamentals for this instrument."}</p>
          <p className="mt-2 text-xs text-stone-500">This is normal for many ETFs, warrants, units and other non-operating-company securities. Price and chart data can still work normally.</p>
        </section>
      )}

      {symbol && (
        <section className="mt-5 rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-baseline justify-between gap-3"><h3 className="font-semibold">Data freshness</h3><span className="text-xs text-stone-500">Cached data is reused until you explicitly refresh or Ledger finds it missing.</span></div>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Freshness label="Price" source={sourceLabel(metrics.price_source)} timestamp={metrics.price_timestamp || metrics.price_updated_at} />
            <Freshness label="Fundamentals" source={metrics.fundamental_source ? "SEC" : "—"} timestamp={metrics.fundamentals_updated_at} detail={metrics.period_end ? `Fiscal period ending ${metrics.period_end}` : null} />
          </div>
        </section>
      )}
    </div>
  );
}

function Metric({ label, value }) { return <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm"><p className="text-xs uppercase tracking-wide text-stone-500">{label}</p><p className="mt-2 text-xl font-semibold tabular-nums">{value}</p></div>; }
function Freshness({ label, source, timestamp, detail }) { return <div className="rounded-lg bg-stone-50 p-4"><p className="text-xs uppercase tracking-wide text-stone-500">{label}</p><p className="mt-1 text-sm font-medium">{source}</p><p className="mt-1 text-xs text-stone-500">{formatStamp(timestamp)}</p>{detail && <p className="mt-1 text-xs text-stone-500">{detail}</p>}</div>; }
