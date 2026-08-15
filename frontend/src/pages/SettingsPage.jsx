import { useState } from "react";

export default function SettingsPage() {
  const [interval, setIntervalMin] = useState(
    localStorage.getItem("priceRefreshMinutes") || "30"
  );
  const [saved, setSaved] = useState(false);

  const save = () => {
    localStorage.setItem("priceRefreshMinutes", interval);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  return (
    <div className="max-w-xl">
      <p className="font-body text-sm text-ink-soft mb-6">
        A couple of notes on refresh rates before you set these:
      </p>
      <div className="font-body text-sm text-ink-soft flex flex-col gap-3 mb-8 border-l-2 border-line pl-4">
        <p>
          <strong className="text-ink">Fundamentals</strong> (P/E, growth, margins) only change
          when companies report — usually quarterly. There's no benefit to
          refreshing these more than once a day, and Yahoo Finance may rate-limit
          you if you poll too aggressively.
        </p>
        <p>
          <strong className="text-ink">Prices</strong> move during trading hours, so a periodic
          refresh has some logic to it. But given the tool is built for steady,
          long-term contributions rather than active trading, a fast refresh
          mostly just invites checking more often than is useful — a stock
          wiggling 0.3% in an hour doesn't change a long-term thesis.
        </p>
      </div>

      <label className="flex flex-col gap-2 mb-6">
        <span className="font-body text-sm text-ink">Portfolio value refresh (minutes)</span>
        <input
          type="number"
          min="5"
          value={interval}
          onChange={(e) => setIntervalMin(e.target.value)}
          className="font-mono text-sm px-3 py-2 border border-line rounded-sm bg-white w-32"
        />
        <span className="font-body text-xs text-ink-soft">
          Set to 0 to only refresh when you manually open the Portfolio page.
        </span>
      </label>

      <button
        onClick={save}
        className="font-body text-sm px-4 py-2 bg-pine text-paper rounded-sm hover:bg-pine-dim"
      >
        {saved ? "Saved" : "Save"}
      </button>
    </div>
  );
}
