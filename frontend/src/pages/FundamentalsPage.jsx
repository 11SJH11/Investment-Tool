import { useState } from "react";
import Card from "../components/Card";
import TickerPicker from "../components/TickerPicker";
import SectorValuationCard from "../components/SectorValuationCard";
import { api } from "../api";

const METRIC_ORDER = [
  "P/E Ratio (trailing)", "P/E Ratio (forward)", "Price/Book",
  "Revenue Growth (YoY)", "Earnings Growth (YoY)", "Profit Margin",
  "Operating Margin", "Debt/Equity", "Return on Equity",
  "Free Cash Flow", "Market Cap", "Dividend Yield",
  "Beta (volatility vs market)", "52-Week High", "52-Week Low",
];

const PERCENT_METRICS = new Set([
  "Revenue Growth (YoY)", "Earnings Growth (YoY)", "Profit Margin",
  "Operating Margin", "Return on Equity", "Dividend Yield",
]);
const CURRENCY_SCALE_METRICS = new Set(["Market Cap", "Free Cash Flow"]);

function formatValue(label, val) {
  if (val === null || val === undefined) return "n/a";
  if (label === "Dividend Yield") {
    const pct = val > 0.15 ? val : val * 100;
    return `${pct.toFixed(2)}%`;
  }
  if (PERCENT_METRICS.has(label)) return `${(val * 100).toFixed(1)}%`;
  if (CURRENCY_SCALE_METRICS.has(label)) {
    if (Math.abs(val) >= 1e12) return `$${(val / 1e12).toFixed(2)}T`;
    if (Math.abs(val) >= 1e9) return `$${(val / 1e9).toFixed(1)}B`;
    return `$${(val / 1e6).toFixed(1)}M`;
  }
  return typeof val === "number" ? val.toFixed(2) : String(val);
}

export default function FundamentalsPage({ tickers, setTickers }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = async (list) => {
    if (!list.length) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.fundamentals(list.join(","));
      setData(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  // Group tickers by asset_class, then by sector within Stock
  const groups = {};
  if (data) {
    for (const [ticker, info] of Object.entries(data)) {
      const cls = info.asset_class || "Unknown";
      const key = cls === "Stock" ? `Stock — ${info.sector}` : cls;
      groups[key] = groups[key] || [];
      groups[key].push(ticker);
    }
  }

  return (
    <div>
      <p className="font-body text-sm text-ink-soft mb-4 max-w-2xl">
        Public fundamentals only — not predictions. Use these to compare how
        the market is pricing each company relative to its growth, margins,
        and risk.
      </p>
      <TickerPicker selected={tickers} onChange={setTickers} />
      <button
        onClick={() => load(tickers)}
        disabled={loading || tickers.length === 0}
        className="font-body text-sm px-4 py-2 bg-pine text-paper rounded-sm hover:bg-pine-dim disabled:opacity-50 mb-6"
      >
        {loading ? "Loading…" : "Load fundamentals"}
      </button>

      {error && (
        <p className="font-body text-sm text-loss mb-4">
          Couldn't load data: {error}
        </p>
      )}

      {data && (
        <div className="flex flex-col gap-6">
          <SectorValuationCard tickers={Object.keys(data)} />
          {Object.entries(groups).map(([groupName, groupTickers]) => (
            <Card key={groupName} eyebrow="Group" title={groupName}>
              <div className="overflow-x-auto">
                <table className="font-mono text-xs tabular-nums w-full">
                  <thead>
                    <tr className="border-b border-line">
                      <th className="text-left py-1.5 pr-4 font-body text-ink-soft font-normal">Metric</th>
                      {groupTickers.map((t) => (
                        <th key={t} className="text-right py-1.5 pl-4 text-ink">{t}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {METRIC_ORDER.map((metric) => (
                      <tr key={metric} className="border-b border-line/50 last:border-0">
                        <td className="py-1.5 pr-4 font-body text-ink-soft whitespace-nowrap">{metric}</td>
                        {groupTickers.map((t) => (
                          <td key={t} className="text-right py-1.5 pl-4 text-ink">
                            {formatValue(metric, data[t].metrics[metric])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
