import { useState, useEffect } from "react";
import Card from "../components/Card";
import TickerAutocomplete from "../components/TickerAutocomplete";
import { api } from "../api";

export default function WatchlistPage() {
  const [tickers, setTickers] = useState([]);
  const [newTicker, setNewTicker] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState(null);

  const loadList = async () => {
    setLoading(true);
    try {
      const res = await api.getWatchlist();
      setTickers(res.tickers);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadList(); }, []);

  const addTicker = async () => {
    if (!newTicker) return;
    try {
      const res = await api.addWatchlistTicker(newTicker);
      setTickers(res.tickers);
      setNewTicker("");
    } catch (e) {
      setError(e.message);
    }
  };

  const removeTicker = async (ticker) => {
    try {
      const res = await api.removeWatchlistTicker(ticker);
      setTickers(res.tickers);
      setData((prev) => prev ? prev.filter((d) => d.ticker !== ticker) : prev);
    } catch (e) {
      setError(e.message);
    }
  };

  const fetchData = async () => {
    setFetching(true);
    setError(null);
    try {
      const res = await api.getWatchlistData();
      setData(res.data);
    } catch (e) {
      setError(e.message);
    } finally {
      setFetching(false);
    }
  };

  return (
    <div>
      <p className="font-body text-sm text-ink-soft mb-4 max-w-2xl">
        Tickers you're keeping an eye on, separate from your actual
        holdings. Starts with a small preset — add or remove anything.
        Fetching live data is a separate step since it's a live call per ticker.
      </p>

      <Card eyebrow="List" title="Your watchlist" className="mb-6">
        {loading ? (
          <p className="font-body text-sm text-ink-soft">Loading…</p>
        ) : (
          <>
            <div className="flex flex-wrap gap-2 mb-3">
              {tickers.map((t) => (
                <span key={t} className="font-mono text-xs bg-line/60 text-ink px-2 py-1 rounded-sm flex items-center gap-1.5">
                  {t}
                  <button onClick={() => removeTicker(t)} className="text-ink-soft hover:text-loss" aria-label={`Remove ${t}`}>×</button>
                </span>
              ))}
              {tickers.length === 0 && <span className="font-body text-xs text-ink-soft italic">Empty — add something below.</span>}
            </div>
            <div className="flex gap-2 mb-3">
              <TickerAutocomplete value={newTicker} onChange={setNewTicker} className="w-40" />
              <button onClick={addTicker} className="font-body text-sm px-4 py-2 bg-pine text-paper rounded-sm hover:bg-pine-dim">
                Add
              </button>
            </div>
            <button
              onClick={fetchData}
              disabled={fetching || tickers.length === 0}
              className="font-body text-sm px-4 py-2 bg-slate text-paper rounded-sm hover:opacity-90 disabled:opacity-50"
            >
              {fetching ? "Fetching…" : "Fetch live data"}
            </button>
          </>
        )}
      </Card>

      {error && <p className="font-body text-sm text-loss mb-4">{error}</p>}

      {data && (
        <Card eyebrow="Snapshot" title="Live data">
          <table className="font-mono text-xs tabular-nums w-full">
            <thead>
              <tr className="border-b border-line">
                <th className="text-left py-1.5 font-body text-ink-soft font-normal">Ticker</th>
                <th className="text-left py-1.5 font-body text-ink-soft font-normal">Name</th>
                <th className="text-right py-1.5 font-body text-ink-soft font-normal">Price</th>
                <th className="text-right py-1.5 font-body text-ink-soft font-normal">Day change</th>
                <th className="text-right py-1.5 font-body text-ink-soft font-normal">P/E</th>
                <th className="text-right py-1.5 font-body text-ink-soft font-normal">Beta</th>
              </tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.ticker} className="border-b border-line/50 last:border-0">
                  <td className="py-1.5">{d.ticker}</td>
                  <td className="py-1.5 font-body text-ink-soft">{d.name}</td>
                  <td className="text-right py-1.5">{d.price !== null ? `$${d.price}` : "n/a"}</td>
                  <td className={`text-right py-1.5 ${d.change_pct >= 0 ? "text-gain" : "text-loss"}`}>
                    {d.change_pct !== null ? `${d.change_pct >= 0 ? "+" : ""}${d.change_pct}%` : "n/a"}
                  </td>
                  <td className="text-right py-1.5">{d.pe_ratio ? d.pe_ratio.toFixed(1) : "n/a"}</td>
                  <td className="text-right py-1.5">{d.beta ? d.beta.toFixed(2) : "n/a"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
