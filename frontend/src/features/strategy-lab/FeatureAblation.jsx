const number=value=>value==null?'Unavailable':Number(value).toFixed(3);

export default function FeatureAblation({family}) {
 const check=family.research_decision?.simplification;
 if(!check)return null;
 return <details className="mt-3">
  <summary>{family.family_id}: single-feature simplification</summary>
  <p className="text-sm mt-2">{check.verdict.replaceAll('_',' ')}</p>
  <p className="text-xs muted">{check.limitation}</p>
  {check.reasons.map(reason=><p key={reason} className="text-sm">{reason}</p>)}
  <div className="overflow-x-auto"><table className="w-full text-sm text-left" aria-label={`${family.family_id} feature ablation`}>
   <thead><tr>{['Scope','Costs','Parent N','Child N','Feature off avg R','Feature on avg R','Difference'].map(h=><th key={h} className="p-2 whitespace-nowrap">{h}</th>)}</tr></thead>
   <tbody>{check.rows.map((row,index)=><tr key={index}>
    <td className="p-2">{row.scope==='full_period'?'Full development period':`${row.start} to ${row.end}`}</td>
    <td className="p-2">{row.cost_multiplier}×</td><td className="p-2">{row.parent_n??'Unavailable'}</td><td className="p-2">{row.child_n??'Unavailable'}</td>
    <td className="p-2">{number(row.parent_average_r)}</td><td className="p-2">{number(row.child_average_r)}</td><td className="p-2">{number(row.delta_average_r)}</td>
   </tr>)}</tbody>
  </table></div>
 </details>;
}
