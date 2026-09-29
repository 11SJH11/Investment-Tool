import {useState} from 'react';
import {orbMetrics,orbBuckets} from './orbDiagnosticBuckets.js';
import {displayDiagnostic as fmt} from './tradeDiagnostics.js';
export default function OrbDiagnosticAnalysis({trades}) {
  const [metric,setMetric]=useState('breakout_range_atr');
  const rows=orbBuckets(trades,metric),measured=trades.length-(rows.at(-1)?.n||0);
  return <section className="insight-panel mt-5"><div className="ui-toolbar"><h3 className="font-semibold">ORB volatility / participation</h3><label>Diagnostic bucket <select className="input" value={metric} onChange={e=>setMetric(e.target.value)}>{orbMetrics.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label></div>
    <p className="muted text-sm mt-2">Entered trades: N = {trades.length}; measured N = {measured}. Fixed descriptive buckets, not optimized thresholds. Rejected and unfilled setup diagnostics remain in full-run JSON. Missing data is separate from zero. Price/volume buckets are instrument-specific; avoid pooling unlike instruments. Low sample: N &lt; 20.</p>
    <div className="table-scroll mt-3"><table className="comparison-grid text-sm"><thead><tr>{['Bucket','N','R sample N','Avg R','Total R','PF (R)','Win %','Avg MFE R (N)','Avg MAE R (N)'].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{rows.map(r=><tr key={r.label}><td>{r.label}</td><td>{r.n}{r.n<20?' · Low sample':''}</td><td>{r.r_n}</td><td>{fmt(r.average_r)}</td><td>{fmt(r.total_r)}</td><td>{fmt(r.profit_factor)}</td><td>{fmt(r.win_rate)}</td><td>{fmt(r.average_mfe)} (N={r.mfe_n})</td><td>{fmt(r.average_mae)} (N={r.mae_n})</td></tr>)}</tbody></table></div>
  </section>;
}
