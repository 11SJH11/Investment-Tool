import { useState, useEffect } from "react";
import Sidebar from "./components/Sidebar";
import FundamentalsPage from "./pages/FundamentalsPage";
import DiversificationPage from "./pages/DiversificationPage";
import BacktestPage from "./pages/BacktestPage";
import PortfolioPage from "./pages/PortfolioPage";
import SettingsPage from "./pages/SettingsPage";
import RiskFilterPage from "./pages/RiskFilterPage";
import WatchlistPage from "./pages/WatchlistPage";
import { api } from "./api";

const PAGE_TITLES = {
  fundamentals: "Fundamentals",
  diversification: "Diversification",
  backtest: "Backtest",
  portfolio: "Portfolio",
  settings: "Settings",
  "risk-filter": "Risk Filter",
  watchlist: "Watchlist",
};

export default function App() {
  const [active, setActive] = useState("portfolio");
  const [tickers, setTickers] = useState(["AAPL", "JNJ", "JPM", "PG", "XOM", "GLD", "DBC"]);
  const [backendUp, setBackendUp] = useState(null);

  useEffect(() => {
    api.health().then(() => setBackendUp(true)).catch(() => setBackendUp(false));
  }, []);

  return (
    // Fixed to the viewport height with no page-level scroll -- the
    // sidebar and the main content each scroll independently below.
    <div className="h-screen flex bg-paper overflow-hidden">
      <Sidebar active={active} onChange={setActive} />
      <main className="flex-1 overflow-y-auto px-10 py-10">
        <div className="mb-6 flex items-baseline justify-between max-w-5xl">
          <h2 className="font-display text-3xl text-ink">{PAGE_TITLES[active]}</h2>
          {backendUp === false && (
            <span className="font-body text-xs text-loss">
              Backend not reachable — is uvicorn running on :8000?
            </span>
          )}
        </div>

        <div className="max-w-5xl">
          {active === "fundamentals" && <FundamentalsPage tickers={tickers} setTickers={setTickers} />}
          {active === "diversification" && <DiversificationPage tickers={tickers} setTickers={setTickers} />}
          {active === "backtest" && <BacktestPage />}
          {active === "portfolio" && <PortfolioPage />}
          {active === "settings" && <SettingsPage />}
          {active === "risk-filter" && <RiskFilterPage />}
          {active === "watchlist" && <WatchlistPage />}
        </div>
      </main>
    </div>
  );
}
