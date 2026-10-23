const number=value=>value==null?'Unavailable':String(value);
export default function AccountSafeguards({evidence,currency}){
 if(!evidence)return null;
 const assessment=evidence.latest_risk_assessment;
 return <section className="mt-4 space-y-2" aria-label="Persisted account safeguards">
  <h3 className="font-semibold">Account safeguards</h3>
  <p className="text-xs muted">Historical diagnostics only. These are not current risk consumption or permission to trade. Shared-account attempt counts include other strategies and must not be added across preparations.</p>
  <p>Account guard: {evidence.guard?.state??'No persisted guard evidence'}</p>
  {evidence.guard?.since&&<p className="text-xs muted">Guard recorded {evidence.guard.since}</p>}
  <p>Recorded account attempts: {number(evidence.recorded_account_attempts)} (all history, not today&apos;s trade count)</p>
  {!assessment?<p className="text-sm muted">No recorded risk assessment.</p>:<>
   <p>Last diagnostic: {assessment.allowed===true?'Passed checks — execution still disabled':assessment.allowed===false?'Rejected':'Unavailable'}</p>
   <p className="text-xs muted">Evaluated {assessment.evaluated_at_ms?new Date(assessment.evaluated_at_ms).toLocaleString():'Unavailable'} · UTC risk day {assessment.risk_day_utc??'Unavailable'}</p>
   {assessment.reasons?.length>0&&<ul className="list-disc pl-5">{assessment.reasons.map(reason=><li key={reason}>{reason.replaceAll('_',' ')}</li>)}</ul>}
   <p>Projected loss budget: {number(assessment.projected_loss_budget)} {currency}</p>
   <p>Projected gross exposure: {number(assessment.projected_gross_exposure)} {currency}</p>
   <p className="text-xs muted">Projections include the proposed entry at assessment time; they are not account balances or current exposure.</p>
  </>}
 </section>;
}
