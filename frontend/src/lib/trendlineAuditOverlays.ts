/**
 * Ledger Trade Audit: stable, point-in-time HTF trendline overlays.
 * No dependency on a specific lightweight-charts major version.
 *
 * Import into the existing trade-audit React chart, then mount the overlays
 * for the selected saved trade (see README.md). The strategy's EntrySignal
 * stores the original line anchors in trade.metadata.chart_drawings.
 *
 * Do NOT reconstruct trendlines using later price action: that would introduce
 * hindsight into historical trade explanations.
 */

type TimestampInput = string | number | { year: number; month: number; day: number };
type Candle = { time: TimestampInput; [key: string]: unknown };

type Line = {
  type: 'trend_line';
  timeframe: string;
  t1: string;
  p1: number;
  t2: string;
  p2: number;
  confirmed_at: string;
  breakout_at: string;
  side: string;
  role?: string;
  style?: { color?: string; width?: number };
};

type Series = { setData(data: Array<{time: number; value: number}>): void };
type LineOptions = Record<string, unknown>;

type Input = {
  trade: { metadata?: Record<string, unknown> | null; [key: string]: unknown };
  candles: Candle[];
  addLineSeries: (options: LineOptions) => Series;
  removeSeries: (series: Series) => void;
};

function epoch(raw: TimestampInput): number {
  if (typeof raw === 'number') return raw > 1e11 ? Math.round(raw / 1000) : raw;
  if (typeof raw === 'object') {
    return Math.floor(Date.UTC(raw.year, raw.month - 1, raw.day) / 1000);
  }
  if (/^\d+$/.test(raw)) {
    const n = Number(raw);
    return n > 1e11 ? Math.round(n / 1000) : n;
  }
  const ms = Date.parse(raw);
  return Number.isFinite(ms) ? Math.floor(ms / 1000) : NaN;
}

function getLines(trade: Input['trade']): Line[] {
  // The saved trade may nest metadata depending on Ledger release; accept
  // these specific known containers, never invent reconstructed line values.
  const candidates = [
    trade.metadata,
    (trade.metadata as Record<string, unknown> | undefined)?.entry_metadata,
    trade.entry_metadata,
    (trade.metadata as Record<string, unknown> | undefined)?.signal_metadata,
  ];
  for (const candidate of candidates) {
    if (!candidate || typeof candidate !== 'object') continue;
    const drawings = (candidate as Record<string, unknown>).chart_drawings;
    if (!Array.isArray(drawings)) continue;
    return drawings.filter((d): d is Line =>
      d != null && d.type === 'trend_line' &&
      typeof d.t1 === 'string' && typeof d.t2 === 'string' &&
      Number.isFinite(d.p1) && Number.isFinite(d.p2) &&
      typeof d.breakout_at === 'string');
  }
  return [];
}

/**
 * Call once when the selected trade/audit candles change; call the returned
 * disposer on unmount, chart reset, or selecting a different trade.
 */
export function addTrendlineTradeAuditOverlays(input: Input): () => void {
  const { candles, trade, addLineSeries, removeSeries } = input;
  if (candles.length < 2) return () => undefined;
  const times = candles.map(c => epoch(c.time)).filter(Number.isFinite);
  if (times.length < 2) return () => undefined;
  const visibleStart = Math.min(...times);
  const visibleEnd = Math.max(...times);
  const ownedSeries: Series[] = [];
  try {
    for (const line of getLines(trade)) {
      const x1 = epoch(line.t1);
      const x2 = epoch(line.t2);
      const breakout = epoch(line.breakout_at);
      if (![x1, x2, breakout, line.p1, line.p2].every(Number.isFinite) || x2 <= x1) continue;

      // Show the original line in view, projected only through the saved break
      // or exit time. Never draw hypothetical future prices past trade exit.
      const exitRaw = (trade.exit_time ?? trade.closed_at) as TimestampInput | undefined;
      const exitAt = exitRaw === undefined ? breakout : epoch(exitRaw);
      const end = Math.min(visibleEnd, Number.isFinite(exitAt) ? Math.max(breakout, exitAt) : breakout);
      const start = Math.max(visibleStart, x1);
      if (end <= start) continue;
      const value = (x: number) => line.p1 + (line.p2 - line.p1) * ((x - x1) / (x2 - x1));
      const color = line.style?.color || (line.side === 'support' ? '#e35e5e' : '#39b89f');
      const series = addLineSeries({
        color, lineWidth: line.style?.width ?? 2,
        lineStyle: line.role === 'confirmation' ? 2 : 0,
        priceLineVisible: false, lastValueVisible: false,
        crosshairMarkerVisible: false, title: `${line.timeframe} ${line.side}`,
      });
      series.setData([{time: start, value: value(start)}, {time: end, value: value(end)}]);
      ownedSeries.push(series);
    }
  } catch (error) {
    for (const series of ownedSeries) removeSeries(series);
    throw error;
  }
  return () => { for (const series of ownedSeries) removeSeries(series); };
}
