const PREFIX = "ledger.drawings.v1";

function key(scope, symbol) {
  return `${PREFIX}:${String(scope || "charts")}:${String(symbol || "").toUpperCase()}`;
}

export function loadDrawings(scope, symbol) {
  if (!symbol) return [];
  try {
    const value = JSON.parse(localStorage.getItem(key(scope, symbol)) || "[]");
    return Array.isArray(value) ? value : [];
  } catch { return []; }
}

export function saveDrawings(scope, symbol, drawings) {
  if (!symbol) return;
  localStorage.setItem(key(scope, symbol), JSON.stringify(drawings || []));
}

export function drawingId(type = "drawing") {
  return `${type}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}
