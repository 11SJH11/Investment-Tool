import { useState, useMemo, useRef, useEffect } from "react";
import { TICKER_CATALOG } from "../tickerCatalog";

// Flatten the catalog once into a simple searchable list.
const ALL_TICKERS = Object.entries(TICKER_CATALOG).flatMap(([group, items]) =>
  items.map((item) => ({ ...item, group }))
);

export default function TickerAutocomplete({ value, onChange, placeholder = "Ticker", className = "" }) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);

  const suggestions = useMemo(() => {
    if (!value || value.length < 1) return [];
    const q = value.toUpperCase();
    return ALL_TICKERS.filter(
      (t) => t.ticker.startsWith(q) || t.name.toUpperCase().includes(q)
    ).slice(0, 8);
  }, [value]);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="relative" ref={containerRef}>
      <input
        value={value}
        onChange={(e) => { onChange(e.target.value.toUpperCase()); setOpen(true); }}
        onFocus={() => setOpen(true)}
        placeholder={placeholder}
        className={`font-mono text-sm px-3 py-2 border border-line rounded-sm bg-white focus:outline-none focus-visible:ring-2 focus-visible:ring-pine ${className}`}
      />
      {open && suggestions.length > 0 && (
        <ul className="absolute z-10 mt-1 w-56 bg-white border border-line rounded-sm shadow-sm max-h-56 overflow-y-auto">
          {suggestions.map((s) => (
            <li key={s.ticker}>
              <button
                type="button"
                onClick={() => { onChange(s.ticker); setOpen(false); }}
                className="w-full text-left px-3 py-1.5 hover:bg-line/40 flex items-baseline gap-2"
              >
                <span className="font-mono text-sm text-ink">{s.ticker}</span>
                <span className="font-body text-xs text-ink-soft truncate">{s.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
