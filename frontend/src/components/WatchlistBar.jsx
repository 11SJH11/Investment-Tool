import { useState } from "react";
import SymbolSearch from "./SymbolSearch";
import { useWatchlist } from "../app/watchlist";

export default function WatchlistBar({ onSelect, compact = false, title = "Watchlist" }) {
  const watchlist = useWatchlist();
  const [adding, setAdding] = useState(false);
  const [query, setQuery] = useState("");
  const choose = (ticker) => { watchlist.add(ticker); setAdding(false); setQuery(""); onSelect?.(ticker); };
  return <div className={`watchlist-bar ${compact ? "compact" : ""}`}>
    <span className="watchlist-title">{title}</span>
    <div className="watchlist-items">
      {watchlist.items.map((symbol) => <div key={symbol} className="watchlist-chip">
        <button type="button" className="watchlist-symbol" onClick={() => onSelect?.(symbol)}>{symbol}</button>
        <button type="button" className="watchlist-remove" title={`Remove ${symbol}`} onClick={() => watchlist.remove(symbol)}>×</button>
      </div>)}
    </div>
    {adding ? <div className="watchlist-add-search"><SymbolSearch value={query} onChange={setQuery} onSelect={(item) => choose(item.ticker)} placeholder="Add ticker" /></div> : <button type="button" className="chart-icon-btn" title="Add to watchlist" onClick={() => setAdding(true)}>＋</button>}
  </div>;
}
