/**
 * DriftBar -- the signature visual of the app. Each holding gets one row:
 * a horizontal track showing its actual allocation as a filled bar, with a
 * tick mark showing where the target sits. When actual drifts far from
 * target, the bar tints toward the caution color instead of pine.
 */
export default function DriftBar({ ticker, actualPct, targetPct, driftThreshold = 5 }) {
  const drift = actualPct - targetPct;
  const isOffTarget = Math.abs(drift) >= driftThreshold;
  const barColor = isOffTarget ? "bg-caution" : "bg-pine";
  const clampedActual = Math.min(Math.max(actualPct, 0), 100);
  const clampedTarget = Math.min(Math.max(targetPct, 0), 100);

  return (
    <div className="flex items-center gap-4 py-2">
      <span className="font-mono text-sm text-ink w-20 shrink-0">{ticker}</span>
      <div className="relative flex-1 h-3 bg-line/50 rounded-sm overflow-visible">
        <div
          className={`absolute left-0 top-0 h-full rounded-sm transition-all ${barColor}`}
          style={{ width: `${clampedActual}%` }}
        />
        <div
          className="absolute top-[-3px] w-[2px] h-[18px] bg-ink"
          style={{ left: `${clampedTarget}%` }}
          title={`Target: ${targetPct.toFixed(0)}%`}
        />
      </div>
      <span className="font-mono text-xs tabular-nums text-ink-soft w-32 shrink-0 text-right">
        {actualPct.toFixed(1)}% <span className="text-line">/</span> {targetPct.toFixed(0)}% target
      </span>
      {isOffTarget && (
        <span className="font-body text-xs text-caution shrink-0">
          {drift > 0 ? "over" : "under"} {Math.abs(drift).toFixed(1)}pp
        </span>
      )}
    </div>
  );
}
