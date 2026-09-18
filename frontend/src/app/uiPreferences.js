// Local presentation preferences only. Jobs and results belong to the server.
export function readUI(key, fallback, storage = globalThis.localStorage) {
  try { const value = JSON.parse(storage.getItem(`ledger.ui.${key}`)); return value ?? fallback; }
  catch { return fallback; }
}
export function writeUI(key, value, storage = globalThis.localStorage) {
  try { storage.setItem(`ledger.ui.${key}`, JSON.stringify(value)); } catch { /* Private/full storage: remain usable. */ }
}
