import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { useWatchlist } from "../app/watchlist";

const TYPE_LABELS = {
  common_stock: "Common stock",
  adr: "ADR",
  reit: "REIT",
  etf: "ETF",
  etn: "ETN",
  spac: "SPAC",
  preferred: "Preferred",
  unit: "Unit",
  warrant: "Warrant",
  right: "Right",
  fund: "Fund",
  other: "Other",
};

export default function SymbolSearch({ value, onChange, onSelect, placeholder = "Search ticker or company" }) {
  const watchlist = useWatchlist();
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const wrapper = useRef(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      const q = value.trim();
      if (!q) { setResults([]); return; }
      api.searchSymbols(q, 8).then((data) => setResults(data.items || [])).catch(() => setResults([]));
    }, 160);
    return () => clearTimeout(timer);
  }, [value]);

  useEffect(() => {
    const close = (event) => {
      if (wrapper.current && !wrapper.current.contains(event.target)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const choose = (item) => {
    onChange(item.ticker);
    onSelect?.(item);
    setOpen(false);
  };

  const submitTicker = async () => {
    const q = value.trim().toUpperCase();
    if (!q || submitting) return;
    setSubmitting(true);
    try {
      let exact = results.find((item) => item.ticker === q);
      if (!exact) {
        const data = await api.searchSymbols(q, 8);
        exact = (data.items || []).find((item) => item.ticker === q);
      }
      if (exact) choose(exact);
      else setOpen(true);
    } catch {
      setOpen(true);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div ref={wrapper} className="relative">
      <input
        value={value}
        onChange={(event) => { onChange(event.target.value.toUpperCase()); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            submitTicker();
          }
        }}
        placeholder={placeholder}
        className="w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm outline-none focus:border-stone-600"
      />
      {open && results.length > 0 && (
        <div className="absolute z-30 mt-1 max-h-72 w-full overflow-auto rounded-md border border-stone-200 bg-white shadow-xl">
          {results.map((item) => (
            <div key={item.ticker} className="flex items-stretch border-b border-stone-100 last:border-b-0 hover:bg-stone-100">
              <button type="button" onClick={() => choose(item)} className="flex min-w-0 flex-1 items-baseline justify-between gap-4 px-3 py-2 text-left">
                <span className="min-w-0 truncate text-sm"><strong className="font-mono">{item.ticker}</strong><span className="ml-3 text-stone-600">{item.name}</span></span>
                <span className="shrink-0 text-right text-xs text-stone-400"><span>{item.exchange || "—"}</span>{item.security_type && <span className="ml-2">· {TYPE_LABELS[item.security_type] || item.security_type}</span>}</span>
              </button>
              <button type="button" className={`favorite-btn mr-2 self-center ${watchlist.has(item.ticker) ? "active" : ""}`} title={watchlist.has(item.ticker) ? "Remove from watchlist" : "Add to watchlist"} onClick={(event) => { event.stopPropagation(); watchlist.toggle(item.ticker); }}>★</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
