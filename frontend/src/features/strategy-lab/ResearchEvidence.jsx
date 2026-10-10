const display=value=>value==null?'Unavailable':Number(value).toFixed(2);
export default function ResearchEvidence({analysis}){
 const a=analysis;
 return <details className="mt-3"><summary>Winner retention, excursions and diagnostic breakdowns</summary>
 <p className="text-xs muted mt-2">{a.day_basis} Low sample means N &lt; 30; these are descriptive findings.</p>
 <p className="text-sm mt-2">MFE {display(a.summary.average_mfe_r)}R (N {a.summary.mfe_n??0}; lower bounds {a.summary.mfe_lower_bound_n??0}) / MAE {display(a.summary.average_mae_r)}R (N {a.summary.mae_n??0})</p>
 <p className="text-sm">Large winners (at least {a.large_winner_threshold_r??2}R): {a.large_winners?.n??'Unavailable'} / Session-close winners: {a.session_close_winners?.n??'Unavailable'}</p>
 {Object.entries(a.breakdowns||{}).map(([dimension,rows])=><details key={dimension} className="mt-2"><summary>{dimension.replaceAll('_',' ')}</summary><div className="overflow-x-auto"><table className="w-full text-sm text-left"><thead><tr>{['Group','N','Avg R','Total R','R PF','Win %','MFE R','MAE R'].map(h=><th className="p-2 whitespace-nowrap" key={h}>{h}</th>)}</tr></thead><tbody>{Object.entries(rows).map(([key,r])=><tr key={key}><th className="p-2 whitespace-nowrap">{key}{r.low_sample?' / Low sample':''}</th><td>{r.n}</td>{[r.average_r,r.total_r,r.profit_factor_r,r.win_rate_pct,r.average_mfe_r,r.average_mae_r].map((v,i)=><td className="p-2 whitespace-nowrap" key={i}>{display(v)}</td>)}</tr>)}</tbody></table></div></details>)}
 {a.fee_stress&&<p className="text-xs muted mt-3">{a.fee_stress.limitation} {a.fee_stress.available?'See exact sensitivity rows in the evidence history below.':'Unavailable: complete recorded P&L and fees are required.'}</p>}
 </details>;
}
