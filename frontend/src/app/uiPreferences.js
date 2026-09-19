// Local presentation preferences only. Jobs and results belong to the server.
export function readUI(key, fallback, storage = globalThis.localStorage) {
  try { const value = JSON.parse(storage.getItem(`ledger.ui.${key}`)); return value ?? fallback; }
  catch { return fallback; }
}
export function writeUI(key, value, storage = globalThis.localStorage) {
  try { storage.setItem(`ledger.ui.${key}`, JSON.stringify(value)); } catch { /* Private/full storage: remain usable. */ }
}

export function resetUI(keys,storage=globalThis.localStorage) {
  for(const key of keys)try{storage.removeItem(`ledger.ui.${key}`);}catch{}
  if(typeof window!=='undefined')window.dispatchEvent(new CustomEvent('ledger:reset-view',{detail:keys}));
}
