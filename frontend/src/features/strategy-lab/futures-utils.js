export function replayEconomics(instrument, size, fill, prices = []) {
  if (instrument?.asset_type !== "future") return {quantity: size / fill, contract_multiplier: 1};
  if (!instrument.execution_supported) throw new Error("Continuous futures are chart-only. Select a supported dated contract for Replay trading.");
  if (!Number.isInteger(size) || size <= 0) throw new Error("Enter a positive whole number of contracts.");
  const tick = Number(instrument.tick_size);
  if (!(tick > 0) || !(instrument.contract_multiplier > 0)) throw new Error("Verified contract economics are required.");
  for (const price of [fill, ...prices].filter(v => v != null)) {
    if (!Number.isFinite(price) || Math.abs(price / tick - Math.round(price / tick)) > 1e-7) throw new Error("Futures prices must respect the contract tick size.");
  }
  return {quantity: size, contract_multiplier: instrument.contract_multiplier};
}
