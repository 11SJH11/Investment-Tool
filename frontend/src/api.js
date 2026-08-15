const BASE_URL = "http://localhost:8000";

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export const api = {
  health: () => request("/api/health"),
  classify: (tickers) => request(`/api/classify?tickers=${encodeURIComponent(tickers)}`),
  fundamentals: (tickers) => request(`/api/fundamentals?tickers=${encodeURIComponent(tickers)}`),
  diversification: (tickers, start = "2022-01-01", threshold = 0.5) =>
    request(`/api/diversification?tickers=${encodeURIComponent(tickers)}&start=${start}&threshold=${threshold}`),
  backtest: (payload) =>
    request("/api/backtest", { method: "POST", body: JSON.stringify(payload) }),

  getPortfolio: () => request("/api/portfolio"),
  getContributionsDetail: () => request("/api/portfolio/contributions"),
  addContribution: (payload) =>
    request("/api/portfolio/contribution", { method: "POST", body: JSON.stringify(payload) }),
  setTarget: (allocation) =>
    request("/api/portfolio/target", { method: "POST", body: JSON.stringify({ allocation }) }),
  portfolioValue: () => request("/api/portfolio/value"),
  priceOnDate: (ticker, date) =>
    request(`/api/price-on-date?ticker=${encodeURIComponent(ticker)}&date=${date}`),
  currentPrice: (ticker) =>
    request(`/api/current-price?ticker=${encodeURIComponent(ticker)}`),

  macro: () => request("/api/macro"),
  sectorValuation: (tickers) => request(`/api/sector-valuation?tickers=${encodeURIComponent(tickers)}`),
  stressTest: (marketMovePct) =>
    request("/api/stress-test", { method: "POST", body: JSON.stringify({ market_move_pct: marketMovePct }) }),

  reviewJournal: () => request("/api/journal/review", { method: "POST" }),

  riskScreen: (tickers, profile = "low", overrides = null) =>
    request("/api/risk-screen", {
      method: "POST",
      body: JSON.stringify({ tickers, profile, overrides }),
    }),
  getRiskCriteria: () => request("/api/risk-criteria"),

  getIndicators: () => request("/api/indicators"),

  getScanUniverses: () => request("/api/scan/universes"),
  startScan: (universe, profile, overrides, minCriteriaPassed, criteria = null) =>
    request("/api/scan/start", {
      method: "POST",
      body: JSON.stringify({
        universe, profile, overrides,
        min_criteria_passed: minCriteriaPassed ?? null,
        criteria,
      }),
    }),
  getScanStatus: (jobId) => request(`/api/scan/status/${jobId}`),

  getWatchlist: () => request("/api/watchlist"),
  addWatchlistTicker: (ticker) =>
    request("/api/watchlist/add", { method: "POST", body: JSON.stringify({ ticker }) }),
  removeWatchlistTicker: (ticker) =>
    request("/api/watchlist/remove", { method: "POST", body: JSON.stringify({ ticker }) }),
  getWatchlistData: () => request("/api/watchlist/data"),
};
