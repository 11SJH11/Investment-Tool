export default function ResearchSearchHistory({family}) {
 const history=family.search_history;
 if(!history)return null;
 const debt=history.debt;
 return <details className="mt-3">
  <summary>{family.family_id}: hypotheses and research debt</summary>
  <p className="text-sm mt-2">{debt.structural_author_requests} structural requests · {debt.structural_drafts} drafts · {debt.rejected_before_execution} rejected before execution · {debt.failed_or_interrupted} failed/interrupted</p>
  <p className="text-sm">{debt.numeric_hypotheses} numeric hypotheses · {debt.numeric_variants_planned} planned numeric variants</p>
  <p className="text-xs muted mt-2">{history.limitation}</p>
  {debt.redacted_scope_records>0&&<p className="text-xs muted">{debt.redacted_scope_records} records withheld because development-only evidence could not be verified.</p>}
  {debt.integrity_errors>0&&<p role="alert">History integrity check failed. Further code authoring is blocked.</p>}
  {history.records.map(record=><article key={`${record.kind}:${record.id}`} className="mt-3 break-words">
   <h5 className="font-semibold">{record.proposal?.description||(record.evidence_scope==='REDACTED_UNVERIFIED_SCOPE'?'Evidence withheld':'Proposal not completed')}</h5>
   <p className="text-xs muted">{record.kind} · {record.status} · {record.preregistration||'PREREGISTERED'}</p>
   {record.proposal?.rationale&&<p className="text-sm">Rationale: {record.proposal.rationale}</p>}
   {record.proposal?.feature&&<p className="text-sm">Change: {record.proposal.feature}</p>}
   {record.proposal?.expected_result&&<p className="text-sm">Expected: {record.proposal.expected_result}</p>}
   {record.proposal?.falsification&&<p className="text-sm">Falsified by: {record.proposal.falsification}</p>}
   {typeof record.challenge==='string'?<p className="text-sm">Challenge: {record.challenge}</p>:record.challenge?.concerns?.map((text,index)=><p className="text-sm" key={index}>Challenge: {text}</p>)}
   {record.manager&&<p className="text-sm">Manager: {record.manager.decision} — {record.manager.explanation}</p>}
   {record.development_outcome&&<p className="text-sm">Development finding: {record.development_outcome.verdict}</p>}
   {record.error&&<p className="text-sm">Stopped: {record.error}</p>}
  </article>)}
 </details>;
}
