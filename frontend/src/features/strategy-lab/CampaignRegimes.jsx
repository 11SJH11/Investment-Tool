const fields=[['name','Regime name',80],['start','Start date'],['end','End date'],['definition','Numerical definition / market conditions',2000],['evidence_source','Evidence source for classification',1000]];
export function CampaignRegimeForm({rows=[],onChange}){
 return <details><summary>Optional declared development regimes</summary>
  <p className="text-xs muted mt-2">Up to three chronological, disjoint periods inside every family's development range. Declare these before results; Ledger does not verify the labels. Each adds eight reserved simulations per structural attempt at original and doubled costs, within the existing time limit. These are separate accounts, not unseen validation or a portfolio.</p>
  {rows.map((row,i)=><fieldset key={i} className="mt-3"><legend>Regime {i+1}</legend><div className="grid gap-2 sm:grid-cols-2">{fields.map(([key,label,maxLength])=><label key={key}>{label}<input className="input" type={['start','end'].includes(key)?'date':'text'} maxLength={maxLength} value={row[key]} onChange={e=>onChange(rows.map((r,j)=>i===j?{...r,[key]:e.target.value}:r))}/></label>)}</div><button className="mini-btn mt-2" type="button" onClick={()=>onChange(rows.filter((_,j)=>i!==j))}>Remove regime</button></fieldset>)}
  <button className="mini-btn mt-2" type="button" disabled={rows.length>=3} onClick={()=>onChange([...rows,Object.fromEntries(fields.map(([key])=>[key,'']))])}>Add declared regime</button>
 </details>;
}
const fmt=v=>v==null?'Unavailable':Number(v).toFixed(2);
export function CampaignRegimeReport({family}){
 const report=family.regime_checks;
 if(!report?.declared_windows?.length)return null;
 return <details className="mt-3"><summary>{family.family_id}: declared regime checks</summary><p className="text-xs muted mt-2">{report.status}. {report.limitation||'User-declared labels are assumptions, not verified classifications. Independent development accounts; no portfolio aggregation.'}</p>
  {report.declared_windows.map(w=><p className="text-sm mt-2" key={w.name}><strong>{w.name}</strong>: {w.start} to {w.end}. {w.definition} — Source: {w.evidence_source}</p>)}
  <div className="overflow-x-auto"><table className="w-full text-sm text-left" aria-label={`${family.family_id} declared regimes`}><thead><tr>{['Regime','Costs','Status','Parent N','Child N','Parent avg R','Child avg R','Child total R','Child PF (R)'].map(h=><th key={h} className="p-2 whitespace-nowrap">{h}</th>)}</tr></thead><tbody>{(report.cells||[]).map(c=><tr key={`${c.window}-${c.cost_multiplier}`}><th className="p-2">{report.declared_windows[c.window-1]?.name}</th><td className="p-2">{c.cost_multiplier}×</td><td className="p-2">{c.status}</td><td className="p-2">{c.parent_summary?.n??'Unavailable'}</td><td className="p-2">{c.summary?.n??'Unavailable'}</td><td className="p-2">{fmt(c.parent_summary?.average_r)}</td><td className="p-2">{fmt(c.summary?.average_r)}</td><td className="p-2">{fmt(c.summary?.total_r)}</td><td className="p-2">{fmt(c.summary?.profit_factor_r)}</td></tr>)}</tbody></table></div>
 </details>;
}
