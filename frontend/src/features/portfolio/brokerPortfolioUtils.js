// Position prices are in instrument currency; wallet facts are in account currency.
export function activitySemantics(facts, kind) {
  if (kind === 'orders') {
    const side = String(facts.order?.side || facts.side || '').toUpperCase();
    return {type:'Order / fill', direction:['BUY','SELL'].includes(side)?side:'Unavailable'};
  }
  const type = kind === 'dividends' ? 'DIVIDEND' : String(facts.type || '').toUpperCase();
  const known = {DEPOSIT:['Deposit','IN'],WITHDRAWAL:['Withdrawal','OUT'],INTEREST:['Interest','IN'],DIVIDEND:['Dividend','IN'],FEE:['Fee','OUT']};
  if (known[type]) return {type:known[type][0],direction:known[type][1]};
  return {type:type.replaceAll('_',' ') || 'Unavailable',direction:['IN','OUT'].includes(facts.direction)?facts.direction:'Unavailable'};
}
export function returnPercent(pnl, cost) {
  return Number.isFinite(pnl) && Number.isFinite(cost) && cost > 0 ? 100 * pnl / cost : null;
}

export function percent(value) {
  return Number.isFinite(value) ? `${value > 0 ? '+' : ''}${value.toFixed(2)}%` : 'Unavailable';
}

export function performanceTone(value) {
  if (!Number.isFinite(value)) return '';
  return value > 0 ? 'positive' : value < 0 ? 'negative' : 'flat';
}

export function performanceStrength(returnPct) {
  // Return percentage is comparable across position sizes, unlike raw P&L.
  // Cap at 25% so an extreme holding never becomes visually overpowering.
  if (!Number.isFinite(returnPct) || returnPct === 0) return 0;
  const scaled = Math.min(Math.abs(returnPct), 25) / 25;
  return Number((7 + scaled * 11).toFixed(2));
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
