import { useState } from "react";
import Card from "../components/Card";
import TickerPicker from "../components/TickerPicker";
import { api } from "../api";

function cellColor(value, isDiagonal) {
  if (isDiagonal) return "bg-line/40 text-ink-soft";
  const abs = Math.abs(value);
  if (abs >= 0.5) return "bg-caution/30 text-ink";
  if (abs >= 0.25) return "bg-slate/15 text-ink";
  return "bg-pine/10 text-ink";
}

export default function DiversificationPage({ tickers, setTickers }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = async (list) => {
    if (list.length < 2) {
      setError("Need at least 2 tickers to check correlation.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await api.diversification(list.join(","));
      setData(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <p className="font-body text-sm text-ink-soft mb-4 max-w-2xl">
        Checks whether your picks actually move independently of each other.
        Two different company names can still be the same bet if they're
        highly correlated — this is where that shows up.
      </p>
      <TickerPicker selected={tickers} onChange={setTickers} />
      <button
        onClick={() => load(tickers)}
        disabled={loading || tickers.length < 2}
        className="font-body text-sm px-4 py-2 bg-pine text-paper rounded-sm hover:bg-pine-dim disabled:opacity-50 mb-6"
      >
        {loading ? "Loading…" : "Check diversification"}
      </button>

      {error && <p className="font-body text-sm text-loss mb-4">{error}</p>}

      {data && (
        <div className="flex flex-col gap-6">
          <Card eyebrow="Correlation" title="Daily return correlation matrix">
            <div className="overflow-x-auto">
              <table className="font-mono text-xs tabular-nums">
                <thead>
                  <tr>
                    <th className="w-16"></th>
                    {data.tickers.map((t) => (
                      <th key={t} className="text-center px-2 py-1 font-body text-ink-soft font-normal">{t}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.tickers.map((rowT) => (
                    <tr key={rowT}>
                      <td className="pr-3 py-1 font-body text-ink-soft">{rowT}</td>
                      {data.tickers.map((colT) => {
                        const val = data.correlation_matrix[rowT]?.[colT];
                        return (
                          <td
                            key={colT}
                            className={`text-center px-2 py-1.5 ${cellColor(val, rowT === colT)}`}
                          >
                            {val?.toFixed(2)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="font-body text-xs text-ink-soft mt-3">
              Shaded cells mark correlation ≥ 0.25 (light) or ≥ 0.5 (stronger) — closer to 1.0 means the two move together, closer to 0 means they move independently.
            </p>
          </Card>

          <Card eyebrow="Flags" title="Overlapping bets">
            {data.flags.length === 0 ? (
              <p className="font-body text-sm text-ink-soft">
                None above the 0.5 threshold — your picks move fairly independently.
              </p>
            ) : (
              <ul className="flex flex-col gap-2">
                {data.flags.map((f, i) => (
                  <li key={i} className="font-body text-sm text-ink flex items-center gap-2">
                    <span className="font-mono text-caution">{f.correlation.toFixed(2)}</span>
                    <span>{f.ticker_a} ↔ {f.ticker_b}</span>
                    {f.reason && <span className="text-ink-soft text-xs">({f.reason})</span>}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
