import { useState, useEffect } from "react";
import Card from "./Card";
import { api } from "../api";

export default function JournalCard() {
  const [entries, setEntries] = useState([]);
  const [ticker, setTicker] = useState("");
  const [note, setNote] = useState("");
  const [exitCondition, setExitCondition] = useState("");
  const [review, setReview] = useState(null);
  const [reviewError, setReviewError] = useState(null);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = () => api.getJournal().then(setEntries).catch((e) => setError(e.message));

  useEffect(() => { load(); }, []);

  const addEntry = async () => {
    if (!ticker || !note) return;
    try {
      await api.addJournalEntry({ ticker: ticker.toUpperCase(), note, exit_condition: exitCondition });
      setTicker(""); setNote(""); setExitCondition("");
      load();
    } catch (e) {
      setError(e.message);
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

  return (
    <Card eyebrow="Discipline" title="Reasoning journal">
      <p className="font-body text-xs text-ink-soft mb-3">
        Write down why you're holding something and what would change your
        mind, while you're thinking clearly. The AI review below only checks
        your current data against these words — it doesn't generate its own
        buy/sell opinions.
      </p>

      <div className="flex flex-col gap-2 mb-4">
        <div className="flex gap-2">
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            placeholder="Ticker"
            className="font-mono text-sm px-2 py-1.5 border border-line rounded-sm bg-white w-24"
          />
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Why you're holding this / your thesis"
            className="font-body text-sm px-2 py-1.5 border border-line rounded-sm bg-white flex-1"
          />
        </div>
        <div className="flex gap-2">
          <input
            value={exitCondition}
            onChange={(e) => setExitCondition(e.target.value)}
            placeholder="Optional: condition that would change your mind (e.g. 'debt/equity exceeds 150')"
            className="font-body text-sm px-2 py-1.5 border border-line rounded-sm bg-white flex-1"
          />
          <button
            onClick={addEntry}
            className="font-body text-xs px-3 py-1.5 bg-pine text-paper rounded-sm hover:bg-pine-dim"
          >
            Add entry
          </button>
        </div>
      </div>

      {error && <p className="font-body text-xs text-loss mb-2">{error}</p>}

      {entries.length > 0 && (
        <ul className="flex flex-col gap-2 mb-4">
          {entries.map((e, i) => (
            <li key={i} className="font-body text-sm border-l-2 border-line pl-3">
              <span className="font-mono text-ink-soft text-xs">{e.date}</span>{" "}
              <span className="font-mono text-ink">{e.ticker}</span> — {e.note}
              {e.exit_condition && (
                <div className="text-xs text-caution mt-0.5">Exit if: {e.exit_condition}</div>
              )}
            </li>
          ))}
        </ul>
      )}

      <button
        onClick={runReview}
        disabled={reviewLoading || entries.length === 0}
        className="font-body text-xs px-3 py-1.5 bg-slate text-paper rounded-sm hover:opacity-90 disabled:opacity-50"
      >
        {reviewLoading ? "Reviewing…" : "Run AI consistency check"}
      </button>

      {reviewError && (
        <p className="font-body text-xs text-ink-soft italic mt-2">
          {reviewError.includes("Ollama") || reviewError.includes("ANTHROPIC_API_KEY")
            ? "No AI backend available. For free + fully private, install Ollama (ollama.com) and run 'ollama pull llama3.1' -- or add ANTHROPIC_API_KEY to the backend's .env. See .env.example."
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
  );
}
