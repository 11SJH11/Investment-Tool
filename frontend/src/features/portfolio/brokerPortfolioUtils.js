// Position prices are in instrument currency; wallet facts are in account currency.
export function returnPercent(pnl, cost) {
  return Number.isFinite(pnl) && Number.isFinite(cost) && cost > 0 ? 100 * pnl / cost : null;
}

export function percent(value) {
  return Number.isFinite(value) ? `${value > 0 ? '+' : ''}${value.toFixed(2)}%` : 'Unavailable';
}

export function brokerDate(value, timeZone = 'UTC') {
  if (!value || !Number.isFinite(new Date(value).getTime())) return 'Unavailable';
  return new Intl.DateTimeFormat('en-GB', {day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit', timeZone}).format(new Date(value));
}

export function positionMetrics(facts) {
  const instrument = facts.instrument || {}, wallet = facts.walletImpact || {};
  // Presentation abbreviation only: routing and stored identity always use the full ticker.
  const ticker = instrument.ticker?.replace(/_[A-Z]+_(EQ|ETF)$/, '') || 'Unavailable';
  return {name:instrument.name || ticker, ticker, quantity:facts.quantity,
    priceCurrency:instrument.currency, walletCurrency:wallet.currency,
    averageCost:facts.averagePricePaid, currentPrice:facts.currentPrice,
    invested:wallet.totalCost, value:wallet.currentValue, pnl:wallet.unrealizedProfitLoss,
    returnPct:wallet.currency ? returnPercent(wallet.unrealizedProfitLoss, wallet.totalCost) : null};
}
