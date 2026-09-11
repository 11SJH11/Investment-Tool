import { useEffect, useState } from "react";

const KEY = "ledger.watchlist";
const DEFAULTS = ["AAPL", "MSFT", "AMD", "NVDA", "SPY", "QQQ"];
const EVENT = "ledger-watchlist-change";

export function loadWatchlist() {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) || "null");
    if (Array.isArray(parsed) && parsed.length) return parsed.map((x) => String(x).trim().toUpperCase()).filter(Boolean);
  } catch { /* fall through */ }
  return [...DEFAULTS];
}

export function saveWatchlist(items) {
  const clean = [...new Set((items || []).map((x) => String(x).trim().toUpperCase()).filter(Boolean))];
  localStorage.setItem(KEY, JSON.stringify(clean));
  window.dispatchEvent(new CustomEvent(EVENT, { detail: clean }));
  return clean;
}

export function addWatchlistSymbol(symbol) {
  const clean = String(symbol || "").trim().toUpperCase();
  if (!clean) return loadWatchlist();
  return saveWatchlist([...loadWatchlist(), clean]);
}

export function removeWatchlistSymbol(symbol) {
  const clean = String(symbol || "").trim().toUpperCase();
  return saveWatchlist(loadWatchlist().filter((item) => item !== clean));
}

export function toggleWatchlistSymbol(symbol) {
  const clean = String(symbol || "").trim().toUpperCase();
  const current = loadWatchlist();
  return current.includes(clean) ? saveWatchlist(current.filter((item) => item !== clean)) : saveWatchlist([...current, clean]);
}

export function useWatchlist() {
  const [items, setItems] = useState(loadWatchlist);
  useEffect(() => {
    const sync = (event) => setItems(event?.detail || loadWatchlist());
    window.addEventListener(EVENT, sync);
    window.addEventListener("storage", sync);
    return () => { window.removeEventListener(EVENT, sync); window.removeEventListener("storage", sync); };
  }, []);
  return {
    items,
    add: (symbol) => setItems(addWatchlistSymbol(symbol)),
    remove: (symbol) => setItems(removeWatchlistSymbol(symbol)),
    toggle: (symbol) => setItems(toggleWatchlistSymbol(symbol)),
    has: (symbol) => items.includes(String(symbol || "").trim().toUpperCase()),
  };
}
