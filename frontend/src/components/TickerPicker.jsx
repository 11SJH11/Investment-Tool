import { useState } from "react";
import { TICKER_CATALOG } from "../tickerCatalog";

const FUTURES_GROUP = "Futures — leveraged, expire, higher risk";

export default function TickerPicker({ selected, onChange }) {
  const [customDraft, setCustomDraft] = useState("");

  const addTicker = (ticker) => {
    const t = ticker.trim().toUpperCase();
    if (t && !selected.includes(t)) onChange([...selected, t]);
  };

  const removeTicker = (ticker) => {
    onChange(selected.filter((t) => t !== ticker));
  };

  const handleDropdownSelect = (e) => {
    if (e.target.value) {
      addTicker(e.target.value);
      e.target.value = "";
    }
  };

  const showFuturesWarning = selected.some((t) => t.endsWith("=F"));

  return (
    <div className="mb-4">
      <div className="flex flex-wrap gap-2 mb-2">
        {selected.map((t) => (
          <span
            key={t}
            className="font-mono text-xs bg-line/60 text-ink px-2 py-1 rounded-sm flex items-center gap-1.5"
          >
            {t}
            <button
              onClick={() => removeTicker(t)}
              className="text-ink-soft hover:text-loss focus:outline-none"
              aria-label={`Remove ${t}`}
            >
              ×
            </button>
          </span>
        ))}
        {selected.length === 0 && (
          <span className="font-body text-xs text-ink-soft italic">No tickers selected yet</span>
        )}
      </div>

      <div className="flex gap-2">
        <select
          onChange={handleDropdownSelect}
          defaultValue=""
          className="font-body text-sm px-3 py-2 border border-line rounded-sm bg-white flex-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-pine"
        >
          <option value="" disabled>+ Add from list…</option>
          {Object.entries(TICKER_CATALOG).map(([group, items]) => (
            <optgroup key={group} label={group}>
              {items.map((item) => (
                <option key={item.ticker} value={item.ticker}>
                  {item.ticker} — {item.name}
                </option>
              ))}
            </optgroup>
          ))}
        </select>

        <input
          value={customDraft}
          onChange={(e) => setCustomDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") { addTicker(customDraft); setCustomDraft(""); }
          }}
          placeholder="Custom ticker"
          className="font-mono text-sm px-3 py-2 border border-line rounded-sm bg-white w-36 focus:outline-none focus-visible:ring-2 focus-visible:ring-pine"
        />
        <button
          onClick={() => { addTicker(customDraft); setCustomDraft(""); }}
          className="font-body text-sm px-3 py-2 bg-pine text-paper rounded-sm hover:bg-pine-dim"
        >
          Add
        </button>
      </div>

      {showFuturesWarning && (
        <p className="font-body text-xs text-caution mt-2">
          You've selected a futures contract — these use leverage and have expiration
          dates, a materially different risk profile than stocks/ETFs.
        </p>
      )}
    </div>
  );
}
