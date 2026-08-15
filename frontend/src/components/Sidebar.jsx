const SECTIONS = [
  { key: "fundamentals", label: "Fundamentals" },
  { key: "diversification", label: "Diversification" },
  { key: "backtest", label: "Backtest" },
  { key: "portfolio", label: "Portfolio" },
  { key: "risk-filter", label: "Risk Filter" },
  { key: "watchlist", label: "Watchlist" },
  { key: "settings", label: "Settings" },
];

export default function Sidebar({ active, onChange }) {
  return (
    // h-screen + overflow-y-auto makes this scroll independently of the
    // main content pane -- it stays put and keeps its own scroll position
    // even as you scroll a long page on the right.
    <aside className="w-56 shrink-0 border-r border-line pr-6 py-10 pl-6 h-screen overflow-y-auto sticky top-0">
      <div className="mb-10">
        <h1 className="font-display text-2xl font-semibold text-ink">Ledger</h1>
        <p className="font-body text-xs text-ink-soft mt-1 tracking-wide">
          Personal investment record
        </p>
      </div>
      <nav className="flex flex-col gap-1">
        {SECTIONS.map((s) => (
          <button
            key={s.key}
            onClick={() => onChange(s.key)}
            className={`text-left font-body text-sm px-3 py-2 rounded-sm transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-pine ${
              active === s.key
                ? "bg-pine text-paper font-medium"
                : "text-ink-soft hover:bg-line/60 hover:text-ink"
            }`}
          >
            {s.label}
          </button>
        ))}
      </nav>
    </aside>
  );
}
