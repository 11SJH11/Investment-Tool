const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

async function request(path, options = {}) {
  const isForm = typeof FormData !== "undefined" && options.body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...(isForm ? {} : { "Content-Type": "application/json" }), ...(options.headers || {}) },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body?.detail;
    let message = `Request failed (${response.status})`;
    if (typeof detail === "string") message = detail;
    else if (Array.isArray(detail)) message = detail.map((item) => item?.msg || JSON.stringify(item)).join("; ");
    else if (detail && typeof detail === "object") message = detail.message || JSON.stringify(detail);
    throw new Error(message);
  }
  return body;
}

function queryString(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== "" && value !== null && value !== undefined) search.set(key, value);
  });
  return search.toString();
}

export const api = {
  health: () => request("/health"),
  dataStatus: () => request("/data/status"),
  autochartistCapabilities: () => request("/data/providers/autochartist/capabilities"),
  refreshSymbols: () => request("/data/symbols/refresh", { method: "POST" }),
  searchSymbols: (query = "", limit = 20) =>
    request(`/symbols?query=${encodeURIComponent(query)}&limit=${limit}`),

  screen: (params) => request(`/screener?${queryString(params)}`),
  refreshScreenerPrices: (limit = null) =>
    request(`/screener/refresh/prices${limit ? `?limit=${limit}` : ""}`, { method: "POST" }),
  refreshScreenerFundamentals: (maxCompanies = null) =>
    request(`/screener/refresh/fundamentals${maxCompanies ? `?max_companies=${maxCompanies}` : ""}`, { method: "POST" }),

  researchItems: (params = {}) => request(`/research/items?${queryString(params)}`),
  saveResearchItem: (payload) => request("/research/items", { method: "POST", body: JSON.stringify(payload) }),
  deleteResearchItem: (id) => request(`/research/items/${id}`, { method: "DELETE" }),
  research: (ticker, refresh = false) =>
    request(`/research/${encodeURIComponent(ticker)}?refresh=${refresh}`),
  researchBars: (ticker, timeframe, lookbackDays, refresh = false, session = "regular") =>
    request(`/research/${encodeURIComponent(ticker)}/bars?${queryString({ timeframe, lookback_days: lookbackDays, refresh, session })}`),
  researchIndicator: (ticker, key, timeframe, lookbackDays, session = "regular", paramsOrLength = {}) => {
    const params = typeof paramsOrLength === "number" ? { length: paramsOrLength } : (paramsOrLength || {});
    return request(`/research/${encodeURIComponent(ticker)}/indicator?${queryString({ key, timeframe, lookback_days: lookbackDays, session, params_json: JSON.stringify(params) })}`);
  },


  portfolio: (account = "") => request(`/portfolio?${queryString({ account })}`),
  addPortfolioTransaction: (payload) => request("/portfolio/transactions", { method: "POST", body: JSON.stringify(payload) }),
  deletePortfolioTransaction: (id) => request(`/portfolio/transactions/${id}`, { method: "DELETE" }),
  refreshPortfolioPrices: (account = "") => request(`/portfolio/refresh-prices?${queryString({ account })}`, { method: "POST" }),

  journalTrades: (params = {}) => request(`/journal/trades?${queryString(params)}`),
  journalTrade: (id) => request(`/journal/trades/${id}`),
  journalOptions: () => request("/journal/options"),
  journalSettings: () => request("/journal/settings"),
  saveJournalSettings: (timezone) => request("/journal/settings", { method: "PUT", body: JSON.stringify({ timezone }) }),
  brokerStatus: () => request("/journal/brokers"),
  syncBrokerTrades: () => request("/journal/brokers/sync", { method: "POST" }),
  dailySummary: (review_date, account, timezone) => request(`/journal/daily-summary?${queryString({ review_date, account, timezone })}`),
  createJournalTrade: (payload) => request("/journal/trades", { method: "POST", body: JSON.stringify(payload) }),
  updateJournalTrade: (id, payload) => request(`/journal/trades/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteJournalTrade: (id) => request(`/journal/trades/${id}`, { method: "DELETE" }),
  journalAnalytics: (filters = {}) => request(`/journal/analytics?${queryString(typeof filters === "string" ? { source: filters } : filters)}`),
  journalReport: (payload) => request("/journal/report", { method: "POST", body: JSON.stringify(payload || {}) }),
  journalCalendar: (month = "", filters = {}) => request(`/journal/calendar?${queryString({ month, ...(typeof filters === "string" ? { source: filters } : filters) })}`),
  dailyReviews: () => request("/journal/daily-reviews"),
  saveDailyReview: (payload) => request("/journal/daily-reviews", { method: "POST", body: JSON.stringify(payload) }),
  playbook: () => request("/journal/playbook"),
  createPlaybook: (payload) => request("/journal/playbook", { method: "POST", body: JSON.stringify(payload) }),
  updatePlaybook: (id, payload) => request(`/journal/playbook/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deletePlaybook: (id) => request(`/journal/playbook/${id}`, { method: "DELETE" }),
  uploadJournalAttachment: (ownerType, ownerId, slot, file, caption = "") => {
    const form = new FormData();
    form.append("owner_type", ownerType); form.append("owner_id", String(ownerId));
    form.append("slot", slot || ""); form.append("caption", caption || ""); form.append("file", file);
    return request("/journal/attachments", { method: "POST", body: form });
  },
  deleteJournalAttachment: (id) => request(`/journal/attachments/${id}`, { method: "DELETE" }),

  strategyLabStrategies: () => request("/strategy-lab/strategies"),
  strategyLabIndicators: () => request("/strategy-lab/indicators"),
  strategyLabRuns: (limit = 100) => request(`/strategy-lab/runs?${queryString({ limit })}`),
  strategyLabRun: (id) => request(`/strategy-lab/runs/${id}`),
  strategyLabExperiment: (group) => request(`/strategy-lab/experiments/${encodeURIComponent(group)}`),
  updateStrategyLabRun: (id, payload) => request(`/strategy-lab/runs/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteStrategyLabRun: (id) => request(`/strategy-lab/runs/${id}`, { method: "DELETE" }),
  runBacktest: (payload) => request("/strategy-lab/backtest", { method: "POST", body: JSON.stringify(payload) }),
  strategyLabAuditBars: (symbol, timeframe, session, entry, exit, beforeBars = 50, afterBars = 20) =>
    request(`/strategy-lab/audit-bars?${queryString({ symbol, timeframe, session, entry, exit, before_bars: beforeBars, after_bars: afterBars })}`),
  strategyLabReplayBars: (symbol, replayDate, replayEndDate, startTime, timeframe = "5m", session = "regular", contextBars = 100, contextDays = null) =>
    request(`/strategy-lab/replay/bars?${queryString({ symbol, replay_date: replayDate, replay_end_date: replayEndDate, start_time: startTime, timeframe, session, context_bars: contextBars, context_days: contextDays })}`),
  strategyLabReplayIndicator: (symbol, replayDate, replayEndDate, startTime, key, timeframe = "5m", session = "regular", contextBars = 100, contextDays = null, params = {}) =>
    request(`/strategy-lab/replay/indicator?${queryString({ symbol, replay_date: replayDate, replay_end_date: replayEndDate, start_time: startTime, key, timeframe, session, context_bars: contextBars, context_days: contextDays, params_json: JSON.stringify(params || {}) })}`),
};

export function backendFileUrl(path) {
  if (!path) return "";
  const origin = API_BASE.replace(/\/api\/?$/, "");
  return path.startsWith("http") ? path : `${origin}${path}`;
}
