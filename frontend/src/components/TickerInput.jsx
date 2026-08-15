import { useState } from "react";

export default function TickerInput({ tickers, onChange, onSubmit, loading }) {
  const [draft, setDraft] = useState(tickers.join(", "));

  const submit = () => {
    const parsed = draft
      .split(",")
      .map((t) => t.trim().toUpperCase())
      .filter(Boolean);
    onChange(parsed);
    onSubmit(parsed);
  };

  return (
    <div className="flex items-center gap-2 mb-6">
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="AAPL, JNJ, JPM, PG, XOM, GLD, DBC"
        className="font-mono text-sm flex-1 px-3 py-2 border border-line rounded-sm bg-white focus:outline-none focus-visible:ring-2 focus-visible:ring-pine"
      />
      <button
        onClick={submit}
        disabled={loading}
        className="font-body text-sm px-4 py-2 bg-pine text-paper rounded-sm hover:bg-pine-dim disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-pine"
      >
        {loading ? "Loading…" : "Load"}
      </button>
    </div>
  );
}
