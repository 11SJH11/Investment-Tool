import { useState } from "react";
import Card from "./Card";
import { api } from "../api";

export default function SectorValuationCard({ tickers }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.sectorValuation(tickers.join(","));
      setData(result.results.filter((r) => r.sector_pe !== null));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card eyebrow="Context" title="Valuation vs. sector baseline">
      <p className="font-body text-xs text-ink-soft mb-3">
        Compares each stock's P/E to its sector ETF's P/E — a fairer comparison
        than pitting a tech stock's multiple against an energy stock's.
      </p>
      <button
        onClick={load}
        disabled={loading}
        className="font-body text-xs px-3 py-1.5 bg-slate text-paper rounded-sm hover:opacity-90 disabled:opacity-50 mb-3"
      >
        {loading ? "Loading…" : "Compare to sector"}
      </button>
      {error && <p className="font-body text-xs text-loss">{error}</p>}
      {data && data.length > 0 && (
        <table className="font-mono text-xs tabular-nums w-full">
          <thead>
            <tr className="border-b border-line">
              <th className="text-left py-1 font-body text-ink-soft font-normal">Ticker</th>
              <th className="text-right py-1 font-body text-ink-soft font-normal">P/E</th>
              <th className="text-right py-1 font-body text-ink-soft font-normal">Sector ETF</th>
              <th className="text-right py-1 font-body text-ink-soft font-normal">Sector P/E</th>
              <th className="text-right py-1 font-body text-ink-soft font-normal">Premium</th>
            </tr>
          </thead>
          <tbody>
            {data.map((r) => (
              <tr key={r.ticker} className="border-b border-line/50 last:border-0">
                <td className="py-1">{r.ticker}</td>
                <td className="text-right py-1">{r.ticker_pe ?? "n/a"}</td>
                <td className="text-right py-1 text-ink-soft">{r.sector_etf}</td>
                <td className="text-right py-1">{r.sector_pe}</td>
                <td className={`text-right py-1 ${r.premium_pct > 0 ? "text-caution" : "text-slate"}`}>
                  {r.premium_pct > 0 ? "+" : ""}{r.premium_pct}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}
