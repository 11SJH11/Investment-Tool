import {excursionAnalysis,displayDiagnostic as fmt} from './tradeDiagnostics.js';
const percentage=(n,total)=>total?`${fmt(100*n/total)}%`:'\u2014';
const exit=(r,key)=>`${r[key]} / ${percentage(r[key],r.n)}`;
function Table({title,rows,columns}) {
  return <section className="mt-5"><h4 className="font-semibold">{title}</h4><div className="table-scroll mt-2"><table className="comparison-grid text-sm"><thead><tr>{columns.map(([key,label])=><th key={key}>{label}</th>)}</tr></thead><tbody>{rows.map(row=><tr key={row.label}>{columns.map(([key,,render])=><td key={key}>{render?render(row):typeof row[key]==='number'?fmt(row[key]):row[key]??'\u2014'}</td>)}</tr>)}</tbody></table></div></section>;
}
export default function ExcursionAnalysis({trades}) {
  const a=excursionAnalysis(trades),s=a.summary;
  const base=[['label','Bucket'],['n','N',r=>`${r.n}${r.n<20?' · Low sample':''}`],['r_n','R sample N'],['win_rate','Win %'],['average_r','Average final R']];
  const exits=[['stop','Stop N / %',r=>exit(r,'stop')],['target','Target N / %',r=>exit(r,'target')],['session_close','Session-close N / %',r=>exit(r,'session_close')]];
  const metrics=[['average_mfe','Average MFE R',s.mfe_n],['median_mfe','Median MFE R',s.mfe_n],['average_mae','Average MAE R',s.mae_n],['median_mae','Median MAE R',s.mae_n],['average_hold','Average hold minutes',s.hold_n],['median_hold','Median hold minutes',s.hold_n],['average_winner','Average winning R',trades.filter(t=>t.r_multiple>0).length],['average_loser','Average losing R',trades.filter(t=>t.r_multiple<0).length],['median_r','Median trade R',s.r_n],['drawdown_r','Max closed-trade drawdown R',s.r_n]];
  return <section className="insight-panel mt-5"><h3 className="font-semibold">Excursion / trade management</h3><p className="muted text-sm mt-2">Descriptive only; N &lt; 20 is a low sample, not evidence of an edge. MFE/MAE are conservative lower bounds excluding ambiguous exit-bar extremes. Times are completed-bar confirmation bounds or exact fills, not intrabar crossing times. Missing measurements stay unavailable.</p>
    <dl className="portfolio-metrics">{metrics.map(([key,label,n])=><div key={key}><dt>{label}</dt><dd>{fmt(s[key])}</dd><small>N = {n}{n<20?' · Low sample':''}</small></div>)}</dl><p className="muted text-xs">R drawdown nets simultaneous exits and requires a complete timestamped R sequence. It is separate from account-% drawdown.</p>
    <Table title="MFE buckets" rows={a.mfe} columns={[...base,['percent','% measured'],['total_r','Total final R'],['profit_factor','PF (R)'],...exits,['average_hold','Average hold min'],['hold_n','Hold N']]}/>
    <Table title="MFE thresholds" rows={a.thresholds} columns={[...base,['percent','% measured'],...exits,['average_time','Average reach min'],['median_time','Median reach min'],['time_n','Timing N']]}/>
    <p className="text-sm mt-4">{a.reversals.map(r=>`Reached ≥ ${r.threshold}R then finished ≤ 0R: N = ${r.n}`).join(' · ')}. Reached ≥ 1R then stopped at −1R ± 0.05R: N = {a.stoppedAfterOne}. Measured MFE sample: N = {s.mfe_n}.</p>
    <Table title="MAE buckets" rows={a.mae} columns={[...base,['average_mfe','Average MFE R'],['mfe_n','MFE N'],['exitCounts','Exit reasons (N)',r=>Object.entries(r.exitCounts).map(([k,v])=>`${k}: ${v}`).join(' · ')||'\u2014']]}/>
  </section>;
}
