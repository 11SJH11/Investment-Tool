import {finite,sampleStats,tradeDiagnostics} from './tradeDiagnostics.js';
const price=[0,.25,.5,1,2,5,10],ratio=[0,.5,1,1.5,2,3,5],unit=[0,.2,.4,.6,.8,1],volume=[0,1000,10000,100000,1000000];
export const orbMetrics=[
  ['breakout_range','Breakout range (price)',price],['prior_1m_atr14','Prior 1m ATR14 (price)',price],
  ['breakout_range_atr','Breakout range / prior ATR',ratio],['breakout_body','Breakout body (price)',price],
  ['breakout_body_ratio','Body / range',unit],['breakout_close_location','Close location (low=0, high=1)',unit],
  ['breakout_volume','Breakout volume',volume],['same_minute_volume_median20','Same-minute median volume (20 sessions)',volume],
  ['breakout_rvol','Breakout same-minute RVOL',ratio],['opening_range_volume','Opening-range volume',volume],
  ['opening_range_volume_median20','Opening-range median volume (20 sessions)',volume],['opening_range_rvol','Opening-range RVOL',ratio],
  ['previous_daily_atr14','Previous daily ATR14 (price)',price],['previous_close','Previous close (price)',[0,25,50,100,250,500,1000,10000]],
  ['daily_natr_pct','Daily NATR %',[0,.5,1,2,3,5,10]],['daily_natr_percentile','Daily NATR percentile',[0,20,40,60,80,100]],
];
export function orbBuckets(trades,key) {
  const spec=orbMetrics.find(m=>m[0]===key);if(!spec)return [];
  const rows=trades.map(t=>({...t,...tradeDiagnostics(t),diagnostic:finite(t.metadata?.[key])}));
  const bounds=spec[2];
  return [...bounds.map((lo,i)=>{const hi=bounds[i+1]??Infinity;return {label:hi===Infinity?`${lo}+`:`${lo}–<${hi}`,...sampleStats(rows.filter(t=>t.diagnostic!=null&&t.diagnostic>=lo&&t.diagnostic<hi))};}),
    {label:'Unavailable',...sampleStats(rows.filter(t=>t.diagnostic==null))}];
}
