import { useState, useEffect } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import Card from "../components/Card";
import TickerPicker from "../components/TickerPicker";
import { TICKER_CATALOG } from "../tickerCatalog";
import { api } from "../api";

const BENCHMARK_OPTIONS = TICKER_CATALOG["Broad Market Benchmarks"];

export default function BacktestPage() {
  const [tickers, setTickers] = useState(["AAPL", "JNJ", "XOM", "GLD", "DBC"]);
  const [weights, setWeights] = useState({ AAPL: 0.3, JNJ: 0.25, XOM: 0.15, GLD: 0.15, DBC: 0.15 });
  const [benchmark, setBenchmark] = useState("VOO");
  const [contribution, setContribution] = useState(500);
  const [start, setStart] = useState("2018-01-01");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Keep weights in sync with the ticker list: new tickers start at 0, removed ones drop out
  useEffect(() => {
    setWeights((prev) => {
      const next = {};
      for (const t of tickers) next[t] = prev[t] ?? 0;
      return next;
    });
  }, [tickers]);

  const totalWeight = Object.values(weights).reduce((a, b) => a + (parseFloat(b) || 0), 0);
  const weightOk = Math.abs(totalWeight - 1.0) < 0.01;

  const run = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    if (!weightOk) {
      setError(`Allocation weights must sum to 1.0 (currently ${totalWeight.toFixed(2)})`);
      setLoading(false);
      return;
    }
    if (tickers.length === 0) {
      setError("Add at least one ticker.");
      setLoading(false);
      return;
    }
    try {
      const res = await api.backtest({
        tickers,
        target_allocation: Object.fromEntries(tickers.map((t) => [t, parseFloat(weights[t]) || 0])),
        monthly_contribution: parseFloat(contribution),
        benchmark_ticker: benchmark.toUpperCase(),
        start,
        rebalance_freq: "Q",
      });
      setResult(res);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  let chartData = [];
  if (result) {
    const byDate = {};
    for (const p of result.strategy_curve) byDate[p.date] = { date: p.date, strategy: p.value };
    for (const p of result.benchmark_curve) byDate[p.date] = { ...byDate[p.date], date: p.date, benchmark: p.value };
    chartData = Object.values(byDate).filter((_, i) => i % 5 === 0);
  }

  return (
    <div>
      <p className="font-body text-sm text-ink-soft mb-4 max-w-2xl">
        Tests a target allocation with regular contributions against real
        historical prices. Past results here don't predict future ones —
        this is a sanity check, not a forecast.
      </p>

      <Card eyebrow="Setup" title="Strategy parameters" className="mb-6">
        <p className="font-body text-xs text-ink-soft mb-2">Pick tickers</p>
        <TickerPicker selected={tickers} onChange={setTickers} />

        {tickers.length > 0 && (
          <div className="mb-4">
            <p className="font-body text-xs text-ink-soft mb-2">Set weights (must sum to 1.0)</p>
            <div className="flex flex-col gap-1.5">
              {tickers.map((t) => (
                <div key={t} className="flex items-center gap-2">
                  <span className="font-mono text-sm w-20">{t}</span>
                  <input
                    type="number"
                    step="0.05"
                    min="0"
                    max="1"
                    value={weights[t] ?? 0}
                    onChange={(e) => setWeights((w) => ({ ...w, [t]: e.target.value }))}
                    className="font-mono text-sm px-2 py-1 border border-line rounded-sm bg-white w-24"
                  />
                </div>
              ))}
            </div>
            <p className={`font-mono text-xs mt-1.5 ${weightOk ? "text-gain" : "text-caution"}`}>
              Total: {totalWeight.toFixed(2)} {weightOk ? "✓" : "— must equal 1.00"}
            </p>
          </div>
        )}

        <div className="flex gap-4">
          <label className="flex flex-col gap-1 flex-1">
            <span className="text-ink-soft text-xs font-body">Benchmark</span>
            <select
              value={benchmark}
              onChange={(e) => setBenchmark(e.target.value)}
              className="font-mono text-sm px-3 py-2 border border-line rounded-sm bg-white"
            >
              {BENCHMARK_OPTIONS.map((b) => (
                <option key={b.ticker} value={b.ticker}>{b.ticker} — {b.name}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 flex-1">
            <span className="text-ink-soft text-xs font-body">Monthly contribution ($)</span>
            <input
              type="number"
              value={contribution}
              onChange={(e) => setContribution(e.target.value)}
              className="font-mono text-sm px-3 py-2 border border-line rounded-sm bg-white"
            />
          </label>
          <label className="flex flex-col gap-1 flex-1">
            <span className="text-ink-soft text-xs font-body">Start date</span>
            <input
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="font-mono text-sm px-3 py-2 border border-line rounded-sm bg-white"
            />
          </label>
        </div>
        <button
          onClick={run}
          disabled={loading}
          className="self-start font-body text-sm px-4 py-2 bg-pine text-paper rounded-sm hover:bg-pine-dim disabled:opacity-50 mt-3"
        >
          {loading ? "Running…" : "Run backtest"}
        </button>
      </Card>

      {error && <p className="font-body text-sm text-loss mb-4">{error}</p>}

      {result && (
        <div className="flex flex-col gap-6">
          <Card eyebrow="Result" title="Strategy vs. benchmark">
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={chartData}>
                <CartesianGrid stroke="#D7D9CE" strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 11, fontFamily: "IBM Plex Mono" }} minTickGap={40} />
                <YAxis tick={{ fontSize: 11, fontFamily: "IBM Plex Mono" }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
                <Tooltip formatter={(v) => `$${v.toFixed(0)}`} contentStyle={{ fontFamily: "IBM Plex Mono", fontSize: 12 }} />
                <Legend wrapperStyle={{ fontFamily: "IBM Plex Sans", fontSize: 12 }} />
                <Line type="monotone" dataKey="strategy" name="Your strategy" stroke="#2F5D50" dot={false} strokeWidth={2} />
                <Line type="monotone" dataKey="benchmark" name={`Benchmark (${benchmark})`} stroke="#5B6E8C" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </Card>

          <div className="grid grid-cols-2 gap-6">
            <PerfCard title="Your Strategy" perf={result.strategy_perf} />
            <PerfCard title={`Benchmark (${benchmark})`} perf={result.benchmark_perf} />
          </div>
        </div>
      )}
    </div>
  );
}

function PerfCard({ title, perf }) {
  const gainColor = perf.total_gain >= 0 ? "text-gain" : "text-loss";
  return (
    <Card title={title}>
      <dl className="font-mono text-sm tabular-nums flex flex-col gap-1.5">
        <Row label="Total contributed" value={`$${perf.total_contributed.toLocaleString()}`} />
        <Row label="Final value" value={`$${perf.final_value.toLocaleString()}`} />
        <Row label="Total gain" value={`$${perf.total_gain.toLocaleString()}`} valueClass={gainColor} />
        <Row label="Annualized return (IRR)" value={`${perf.annualized_return_pct}%`} valueClass={gainColor} />
        <Row label="Max drawdown" value={`${perf.max_drawdown_pct}%`} valueClass="text-loss" />
      </dl>
    </Card>
  );
}

function Row({ label, value, valueClass = "text-ink" }) {
  return (
    <div className="flex justify-between">
      <dt className="font-body text-ink-soft">{label}</dt>
      <dd className={valueClass}>{value}</dd>
    </div>
  );
}
