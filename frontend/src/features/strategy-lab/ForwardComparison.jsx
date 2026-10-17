const value=n=>n==null?'Unavailable':Number(n).toFixed(3);
export default function ForwardComparison({report}){
 if(!report)return null;
 return <details className="mt-3"><summary>B shadow / paper comparison · {report.matched} matched closed trades</summary>
 <p className="text-xs muted mt-2">{report.limitation}</p>
 <p className="text-xs muted mt-2">Descriptive comparison only. Small samples do not establish an edge. P&amp;L differences can include different position sizes and costs.</p>
 <div className="overflow-x-auto mt-3"><table className="w-full text-sm text-left"><thead><tr>{['Decision (UTC)','Status','Shadow Journal IDs','Paper Journal IDs','Entry slippage / share','Exit slippage / share','P&L difference','Duration difference (s)'].map(h=><th key={h} className="p-2 whitespace-nowrap">{h}</th>)}</tr></thead>
 <tbody>{report.items.map((r,i)=><tr key={i}><td className="p-2 whitespace-nowrap">{r.decision_at}</td><td className="p-2">{r.status.replaceAll('_',' ')}</td><td className="p-2">{r.shadow_journal_ids.join(', ')||'—'}</td><td className="p-2">{r.paper_journal_ids.join(', ')||'—'}</td>{['entry_slippage_per_share','exit_slippage_per_share','pnl_difference','duration_difference_seconds'].map(k=><td key={k} className="p-2">{value(r[k])}</td>)}</tr>)}</tbody></table></div>
 {report.unresolved.length>0&&<p className="text-sm mt-2">Evidence unavailable for {report.unresolved.length} closed trades: {report.unresolved.map(r=>`${r.mode} Journal #${r.journal_id}`).join(', ')}.</p>}
 {!report.items.length&&!report.unresolved.length&&<p className="text-sm mt-2">No closed B trades have been journaled yet.</p>}
 </details>;
}
