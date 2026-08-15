import { useState, useEffect, useRef } from "react";
import Card from "../components/Card";
import DriftBar from "../components/DriftBar";
import MacroPanel from "../components/MacroPanel";
import StressTestCard from "../components/StressTestCard";
import TickerAutocomplete from "../components/TickerAutocomplete";
import { api } from "../api";

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

export default function PortfolioPage() {
  const [portfolio, setPortfolio] = useState(null);
  const [valueData, setValueData] = useState(null);
  const [contributionsDetail, setContributionsDetail] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const [allocationText, setAllocationText] = useState("");

  // Merged log + reasoning form
  const [ticker, setTicker] = useState("");
  const [buyDate, setBuyDate] = useState(todayISO());
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [exitCondition, setExitCondition] = useState("");
  const [pricePreview, setPricePreview] = useState(null); // {price, date_used, exact_match}
  const [pricePreviewError, setPricePreviewError] = useState(null);
  const [currentPricePreview, setCurrentPricePreview] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const previewDebounce = useRef(null);

  // Reasoning journal AI review
  const [review, setReview] = useState(null);
  const [reviewError, setReviewError] = useState(null);
  const [reviewLoading, setReviewLoading] = useState(false);

  const loadAll = async () => {
    setLoading(true);
    try {
      const p = await api.getPortfolio();
      setPortfolio(p);
      setAllocationText(
        Object.entries(p.target_allocation).map(([t, w]) => `${t}:${w}`).join(", ")
      );
      if (Object.keys(p.holdings).length > 0) {
        try {
          const v = await api.portfolioValue();
          setValueData(v);
        } catch (e) {
          setError(`Loaded portfolio, but couldn't fetch live prices: ${e.message}`);
        }
        try {
          const cd = await api.getContributionsDetail();
          setContributionsDetail(cd.contributions);
        } catch (e) {
          // non-fatal -- holdings table still works without per-transaction detail
        }
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadAll(); }, []);

  // Live price preview: whenever ticker + date are both filled, fetch what
  // the price WOULD be, debounced so we're not hammering the API on every keystroke.
  useEffect(() => {
    if (previewDebounce.current) clearTimeout(previewDebounce.current);
    setPricePreview(null);
    setPricePreviewError(null);
    if (!ticker || !buyDate) return;

    previewDebounce.current = setTimeout(async () => {
      try {
        const preview = await api.priceOnDate(ticker.toUpperCase(), buyDate);
        setPricePreview(preview);
      } catch (e) {
        setPricePreviewError(e.message);
      }
    }, 500);

    return () => clearTimeout(previewDebounce.current);
  }, [ticker, buyDate]);

  // Live current-price preview: whenever ticker changes, show "price now"
  // right away so you can eyeball price-then vs. price-now before submitting.
  useEffect(() => {
    setCurrentPricePreview(null);
    if (!ticker) return;
    const t = setTimeout(async () => {
      try {
        const res = await api.currentPrice(ticker.toUpperCase());
        setCurrentPricePreview(res.price);
      } catch (e) {
        // silent -- not critical, the field just stays blank
      }
    }, 500);
    return () => clearTimeout(t);
  }, [ticker]);

  const saveTarget = async () => {
    const allocation = {};
    allocationText.split(",").forEach((entry) => {
      const [t, w] = entry.split(":").map((s) => s.trim());
      if (t && w) allocation[t.toUpperCase()] = parseFloat(w);
    });
    try {
      await api.setTarget(allocation);
      await loadAll();
    } catch (e) {
      setError(e.message);
    }
  };

  const logContribution = async () => {
    if (!ticker || !amount) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.addContribution({
        ticker: ticker.toUpperCase(),
        amount: parseFloat(amount),
        date: buyDate,
        note,
        exit_condition: exitCondition,
      });
      setTicker(""); setAmount(""); setNote(""); setExitCondition("");
      setBuyDate(todayISO());
      setPricePreview(null);
      setCurrentPricePreview(null);
      await loadAll();
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const runReview = async () => {
    setReviewLoading(true);
    setReviewError(null);
    setReview(null);
    try {
      const result = await api.reviewJournal();
      setReview(result);
    } catch (e) {
      setReviewError(e.message);
    } finally {
      setReviewLoading(false);
    }
  };

  if (loading) return <p className="font-body text-sm text-ink-soft">Loading…</p>;

  const holdings = valueData?.holdings || {};
  const hasHoldings = Object.keys(holdings).length > 0;

  return (
    <div className="flex flex-col gap-6">
      <p className="font-body text-sm text-ink-soft max-w-2xl">
        Your real record — nothing here executes trades. Log what you
        actually bought (even weeks ago), why, and this tracks drift from
        your target so you know when (and what) to rebalance.
      </p>

      {error && <p className="font-body text-sm text-loss">{error}</p>}

      <MacroPanel />

      <Card eyebrow="Drift" title="Allocation vs. target">
        {!hasHoldings ? (
          <p className="font-body text-sm text-ink-soft">
            No contributions logged yet — add one below to see your drift chart.
          </p>
        ) : (
          <div className="flex flex-col">
            {Object.entries(holdings).map(([t, info]) => (
              <DriftBar
                key={t}
                ticker={t}
                actualPct={info.current_allocation_pct}
                targetPct={(portfolio.target_allocation[t] || 0) * 100}
              />
            ))}
          </div>
        )}
      </Card>

      {hasHoldings && (
        <Card eyebrow="Holdings" title="Current value (aggregated by ticker)">
          <table className="font-mono text-xs tabular-nums w-full">
            <thead>
              <tr className="border-b border-line">
                <th className="text-left py-1.5 font-body text-ink-soft font-normal">Ticker</th>
                <th className="text-right py-1.5 font-body text-ink-soft font-normal">Shares</th>
                <th className="text-right py-1.5 font-body text-ink-soft font-normal">Invested</th>
                <th className="text-right py-1.5 font-body text-ink-soft font-normal">Value</th>
                <th className="text-right py-1.5 font-body text-ink-soft font-normal">Gain/Loss</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(holdings).map(([t, info]) => (
                <tr key={t} className="border-b border-line/50 last:border-0">
                  <td className="py-1.5">{t}</td>
                  <td className="text-right py-1.5">{info.shares.toFixed(3)}</td>
                  <td className="text-right py-1.5">${info.invested.toFixed(2)}</td>
                  <td className="text-right py-1.5">${info.value.toFixed(2)}</td>
                  <td className={`text-right py-1.5 ${info.gain_loss >= 0 ? "text-gain" : "text-loss"}`}>
                    {info.gain_loss >= 0 ? "+" : ""}{info.gain_loss_pct.toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <Card eyebrow="Setup" title="Target allocation">
        <div className="flex gap-2 items-center">
          <input
            value={allocationText}
            onChange={(e) => setAllocationText(e.target.value)}
            placeholder="AAPL:0.3, JNJ:0.25, GLD:0.15"
            className="font-mono text-sm flex-1 px-3 py-2 border border-line rounded-sm bg-white"
          />
          <button
            onClick={saveTarget}
            className="font-body text-sm px-4 py-2 bg-pine text-paper rounded-sm hover:bg-pine-dim"
          >
            Save target
          </button>
        </div>
      </Card>

      <Card eyebrow="Record" title="Log a buy + your reasoning">
        <p className="font-body text-xs text-ink-soft mb-3">
          Enter what you bought and when — even weeks ago. Price is fetched
          automatically for that date; you don't need to look it up. Write
          your thesis here too, at the same time, so it's saved together
          with the buy rather than as a separate step.
        </p>

        <div className="flex flex-col gap-3">
          <div className="flex gap-3 items-end flex-wrap">
            <label className="flex flex-col gap-1">
              <span className="font-body text-xs text-ink-soft">Ticker</span>
              <TickerAutocomplete value={ticker} onChange={setTicker} className="w-24" />
            </label>
            <label className="flex flex-col gap-1">
              <span className="font-body text-xs text-ink-soft">Date bought</span>
              <input type="date" value={buyDate} max={todayISO()} onChange={(e) => setBuyDate(e.target.value)}
                className="font-mono text-sm px-3 py-2 border border-line rounded-sm bg-white" />
            </label>
            <label className="flex flex-col gap-1">
              <span className="font-body text-xs text-ink-soft">Amount ($)</span>
              <input value={amount} onChange={(e) => setAmount(e.target.value)}
                type="number" className="font-mono text-sm px-3 py-2 border border-line rounded-sm bg-white w-28" />
            </label>

            <div className="flex flex-col gap-1">
              <span className="font-body text-xs text-ink-soft">Price paid (auto)</span>
              <div className="font-mono text-sm px-3 py-2 border border-line rounded-sm bg-line/30 w-28">
                {pricePreview ? `$${pricePreview.price}` : pricePreviewError ? "—" : "…"}
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <span className="font-body text-xs text-ink-soft">Price now</span>
              <div className="font-mono text-sm px-3 py-2 border border-line rounded-sm bg-line/30 w-28">
                {currentPricePreview ? `$${currentPricePreview}` : "…"}
              </div>
            </div>
          </div>

          {pricePreview && !pricePreview.exact_match && (
            <p className="font-body text-xs text-caution">
              {buyDate} wasn't a trading day — using the closest prior trading day, {pricePreview.date_used}.
            </p>
          )}
          {pricePreviewError && (
            <p className="font-body text-xs text-loss">Couldn't fetch price: {pricePreviewError}</p>
          )}

          <label className="flex flex-col gap-1">
            <span className="font-body text-xs text-ink-soft">Why you bought it / your thesis</span>
            <input value={note} onChange={(e) => setNote(e.target.value)}
              className="font-body text-sm px-3 py-2 border border-line rounded-sm bg-white" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-body text-xs text-ink-soft">
              Optional: condition that would change your mind (e.g. "debt/equity exceeds 150")
            </span>
            <input value={exitCondition} onChange={(e) => setExitCondition(e.target.value)}
              className="font-body text-sm px-3 py-2 border border-line rounded-sm bg-white" />
          </label>

          <button
            onClick={logContribution}
            disabled={submitting || !ticker || !amount}
            className="self-start font-body text-sm px-4 py-2 bg-pine text-paper rounded-sm hover:bg-pine-dim disabled:opacity-50"
          >
            {submitting ? "Saving…" : "Log it"}
          </button>
        </div>
      </Card>

      {contributionsDetail.length > 0 && (
        <Card eyebrow="History" title="Every logged buy — price then vs. now">
          <div className="flex flex-col gap-3">
            {contributionsDetail.map((c, i) => (
              <div key={i} className="border-l-2 border-line pl-3">
                <div className="flex items-baseline gap-2 font-mono text-sm">
                  <span className="text-ink">{c.ticker}</span>
                  <span className="text-ink-soft text-xs">{c.date}</span>
                  <span className="text-ink-soft">
                    ${c.price_paid} → {c.price_now !== null ? `$${c.price_now}` : "n/a"}
                  </span>
                  {c.gain_loss_pct !== null && (
                    <span className={c.gain_loss_pct >= 0 ? "text-gain" : "text-loss"}>
                      {c.gain_loss_pct >= 0 ? "+" : ""}{c.gain_loss_pct.toFixed(1)}%
                    </span>
                  )}
                </div>
                {c.note && <p className="font-body text-sm text-ink-soft mt-0.5">{c.note}</p>}
                {c.exit_condition && (
                  <p className="font-body text-xs text-caution mt-0.5">Exit if: {c.exit_condition}</p>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {hasHoldings && <StressTestCard />}

      <Card eyebrow="Discipline" title="AI consistency check">
        <p className="font-body text-xs text-ink-soft mb-3">
          Checks your current holdings/metrics against the reasoning you
          wrote when you logged each buy — flags contradictions or met exit
          conditions. It never generates its own buy/sell opinions.
        </p>
        <button
          onClick={runReview}
          disabled={reviewLoading || !hasHoldings}
          className="font-body text-xs px-3 py-1.5 bg-slate text-paper rounded-sm hover:opacity-90 disabled:opacity-50"
        >
          {reviewLoading ? "Reviewing…" : "Run AI consistency check"}
        </button>

        {reviewError && (
          <p className="font-body text-xs text-ink-soft italic mt-2">
            {reviewError.includes("Ollama") || reviewError.includes("ANTHROPIC_API_KEY")
              ? "No AI backend available. For free + private, install Ollama (ollama.com) and run 'ollama pull llama3.1' — or add ANTHROPIC_API_KEY to the backend's .env."
              : `Couldn't run review: ${reviewError}`}
          </p>
        )}

        {review && (
          <div className="mt-3">
            <p className="font-body text-sm text-ink mb-2">{review.summary}</p>
            {review.flags?.length > 0 && (
              <ul className="flex flex-col gap-2">
                {review.flags.map((f, i) => (
                  <li key={i} className="font-body text-sm border-l-2 border-caution pl-3">
                    <span className="font-mono text-ink">{f.ticker}</span>{" "}
                    <span className="text-xs text-ink-soft">({f.type.replace(/_/g, " ")})</span>
                    <div className="text-ink-soft text-xs mt-0.5">{f.explanation}</div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
