export const warmActive = job => ['queued','running','pausing'].includes(job.status);
export function warmRange(values) {
  return values?.length === 2 ? values.map(value => new Date(value).toISOString().slice(0,16).replace('T',' ')).join(' to ') + ' UTC' : 'Not yet covered';
}
export function warmRequest(symbols, days) {
  const lookback_days = Number(days);
  if (!Number.isInteger(lookback_days) || lookback_days < 1 || lookback_days > 3650) throw new Error('Choose 1 to 3650 days');
  return {symbols:[...symbols],timeframe:'1m',lookback_days,refresh:false};
}
export function canResume(job, now=Date.now()) {
  return ['paused','failed'].includes(job.status) && (!job.retry_at || Date.parse(job.retry_at)<=now);
}
