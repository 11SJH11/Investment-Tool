import { useState } from "react";
import Card from "./Card";
import { api } from "../api";

export default function StressTestCard() {
  const [marketMove, setMarketMove] = useState(-20);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.stressTest(parseFloat(marketMove));
      setResult(res);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card eyebrow="Scenario" title="Market drop stress test">
      <p className="font-body text-xs text-ink-soft mb-3">
        Rough estimate based on each holding's historical beta — not a
        prediction of what will actually happen, just a gut-check on your
        current exposure.
      </p>
      <div className="flex items-center gap-2 mb-3">
        <label className="font-body text-xs text-ink-soft">Hypothetical market move:</label>
        <input
          type="number"
          value={marketMove}
          onChange={(e) => setMarketMove(e.target.value)}
          className="font-mono text-sm px-2 py-1 border border-line rounded-sm bg-white w-20"
        />
        <span className="font-body text-xs text-ink-soft">%</span>
        <button
          onClick={run}
          disabled={loading}
          className="font-body text-xs px-3 py-1.5 bg-slate text-paper rounded-sm hover:opacity-90 disabled:opacity-50 ml-2"
        >
          {loading ? "Running…" : "Run"}
        </button>
      </div>
      {error && <p className="font-body text-xs text-loss">{error}</p>}
      {result && result.portfolio_estimated_move_pct !== null && (
        <div>
          <p className="font-mono text-sm mb-2">
            Estimated portfolio impact:{" "}
            <span className={result.portfolio_estimated_move_pct < 0 ? "text-loss" : "text-gain"}>
              {result.portfolio_estimated_move_pct}% (${result.portfolio_estimated_dollar_change.toLocaleString()})
            </span>
          </p>
          <table className="font-mono text-xs tabular-nums w-full">
            <thead>
              <tr className="border-b border-line">
                <th className="text-left py-1 font-body text-ink-soft font-normal">Ticker</th>
                <th className="text-right py-1 font-body text-ink-soft font-normal">Beta</th>
                <th className="text-right py-1 font-body text-ink-soft font-normal">Est. move</th>
                <th className="text-right py-1 font-body text-ink-soft font-normal">Est. $ change</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(result.holdings).map(([ticker, h]) => (
                <tr key={ticker} className="border-b border-line/50 last:border-0">
                  <td className="py-1">{ticker}</td>
                  <td className="text-right py-1">{h.beta}</td>
                  <td className={`text-right py-1 ${h.estimated_move_pct < 0 ? "text-loss" : "text-gain"}`}>
                    {h.estimated_move_pct}%
                  </td>
                  <td className={`text-right py-1 ${h.estimated_dollar_change < 0 ? "text-loss" : "text-gain"}`}>
                    ${h.estimated_dollar_change.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
