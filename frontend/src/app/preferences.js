export const DEFAULT_NAV = ["Dashboard","Charts","Replay","Backtest","Journal","Investment Portfolio","Screener","Settings"];
export const DEFAULT_PREFS = {
  theme: "dark",
  accent: "blue",
  density: "comfortable",
  chartGridVisible: true, chartVolumeVisible: true, chartCrosshair: true, chartAutoScale: true, chartVisibleBars: 180,
  replayContext: "5d", replaySpeed: 1, replayFollow: false, replayAutoJournal: true, replayConfirm: false, replayHelp: true,
  backtestSizing: "risk_pct", backtestSession: "auto", backtestCapital: 10000, backtestRisk: 1, backtestCommission: 0,
  timeZone: "America/New_York",
  chartSession: "regular",
  chartTimeframe: "5m",
  drawingMagnet: "weak",
  drawingColor: "#60a5fa",
  chartUp: "#22c55e",
  chartDown: "#ef4444",
  chartBackground: "#111111",
  chartGrid: "#262626",
  navOrder: DEFAULT_NAV,
};
export function loadPreferences() {
  try { return { ...DEFAULT_PREFS, ...(JSON.parse(localStorage.getItem("ledger.preferences") || "{}")) }; }
  catch { return { ...DEFAULT_PREFS }; }
}
export function savePreferences(prefs) { localStorage.setItem("ledger.preferences", JSON.stringify(prefs)); applyPreferences(prefs); }
export function applyPreferences(prefs) {
  const root = document.documentElement;
  let dark = prefs.theme === "dark";
  if (prefs.theme === "system") dark = window.matchMedia?.("(prefers-color-scheme: dark)")?.matches;
  root.dataset.theme = dark ? "dark" : "light";
  root.dataset.accent = prefs.accent || "stone";
  root.dataset.density = prefs.density || "comfortable";
  root.style.setProperty("--ledger-candle-up", prefs.chartUp || DEFAULT_PREFS.chartUp);
  root.style.setProperty("--ledger-candle-down", prefs.chartDown || DEFAULT_PREFS.chartDown);
  root.style.setProperty("--ledger-chart-background", prefs.chartBackground || DEFAULT_PREFS.chartBackground);
  root.style.setProperty("--ledger-chart-grid", prefs.chartGrid || DEFAULT_PREFS.chartGrid);
  localStorage.setItem("ledger.timeZone", prefs.timeZone || DEFAULT_PREFS.timeZone);
  localStorage.setItem("ledger.chartSession", prefs.chartSession || DEFAULT_PREFS.chartSession);
  localStorage.setItem("ledger.chartTimeframe", prefs.chartTimeframe || DEFAULT_PREFS.chartTimeframe);
  localStorage.setItem("ledger.drawingMagnet", prefs.drawingMagnet || DEFAULT_PREFS.drawingMagnet);
  localStorage.setItem("ledger.drawingColor", prefs.drawingColor || DEFAULT_PREFS.drawingColor);
}
