export function replaySource(instrument, bar = {}) {
  if (instrument?.asset_type !== 'future') return null;
  if (bar.adjustment_method && bar.adjustment_method !== 'none' || bar.adjustment_mode && bar.adjustment_mode !== 'raw' || Number(bar.price_adjustment || 0) !== 0) throw new Error('Replay fills require raw dated-contract prices.');
  if (instrument.security_type === 'continuous_future') {
    const match = /^([A-Z][A-Z0-9]{0,4})[FGHJKMNQUVXZ]\d{1,2}$/.exec(bar.source_contract || '');
    if (!match || match[1] !== instrument.root || bar.continuous_alias !== instrument.ticker || bar.provider !== 'massive' || !['prior-session-volume45-v1','calendar-front-v1'].includes(bar.roll_schedule_version)) throw new Error('Continuous Replay needs verified source-contract provenance. Reload the data.');
  }
  return bar.source_contract || instrument.ticker;
}

export function replayRollAction(instrument, bar, position, order) {
  const source = replaySource(instrument,bar);
  if (source && position && position.source_contract !== source) throw new Error('Replay terminated: open position crosses a contract roll. No cross-roll fill was made. Start a new Replay session.');
  return source && order && order.source_contract !== source ? 'cancel_order' : null;
}

export function replayEconomics(instrument, size, fill, prices = [], bar = {}) {
  if (instrument?.asset_type !== "future") return {quantity: size / fill, contract_multiplier: 1};
  if (!instrument.execution_supported) throw new Error("Continuous futures are chart-only. Select a supported dated contract for Replay trading.");
  replaySource(instrument,bar);
  if (!Number.isInteger(size) || size <= 0) throw new Error("Enter a positive whole number of contracts.");
  const tick = Number(instrument.tick_size);
  if (!(tick > 0) || !(instrument.contract_multiplier > 0)) throw new Error("Verified contract economics are required.");
  for (const price of [fill, ...prices].filter(v => v != null)) {
    if (!Number.isFinite(price) || Math.abs(price / tick - Math.round(price / tick)) > 1e-7) throw new Error("Futures prices must respect the contract tick size.");
  }
  return {quantity: size, contract_multiplier: instrument.contract_multiplier};
}
