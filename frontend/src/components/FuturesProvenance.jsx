export default function FuturesProvenance({bars = []}) {
  const last = bars.at(-1);
  if (!last?.continuous_alias) return null;
  const rolls = bars.filter((bar,i)=>i && bar.source_contract !== bars[i-1].source_contract);
  return <div className="px-3 py-2 text-xs text-stone-500">
    {last.continuous_alias} → {last.source_contract} · {last.adjustment_mode} · {last.provider}
    <details><summary className="cursor-pointer">Roll schedule / {rolls.length} visible transitions</summary>
      <p>{last.roll_schedule_version}. Ledger volume policy; TradingView parity unverified. Expiry fallback is recorded when no crossover is observed.</p>
      {rolls.map(bar=><p key={bar.timestamp}>{bar.roll_effective_at} → {bar.source_contract} ({bar.roll_method})</p>)}
    </details>
  </div>;
}
