import ResearchDiagnostics from './ResearchDiagnostics.jsx';
const cost=value=>value==null?'Unknown':`$${(value/1000000).toFixed(4)}`;
export default function CampaignOperations({data}){
 if(!data?.model_operations?.length&&!data?.sandbox_operations?.length)return null;
 return <><ResearchDiagnostics operations={data.model_operations}/><article className="insight-panel" aria-label="Recorded model operations">
  <h4 className="font-semibold">Model operations</h4>
  <p className="text-xs muted">{data.limitation}</p>
  {(data.model_operations||[]).map(op=><div key={op.id} className="mt-3 text-sm">
   <p>{op.family_id} · {op.kind} · {op.status}</p>
   <p className="text-xs muted break-all">Operation {op.id}</p>
   {op.operation.role&&<p>{op.operation.role}: {op.operation.status} · {op.elapsed_seconds==null?'Duration unavailable':`${Math.floor(op.elapsed_seconds)} seconds elapsed`}</p>}
   <p>Calls reserved: {op.reserved_calls??'Unknown'} · Returned usage: {op.returned_usage_calls}</p>
   <p>Cost reserved: {cost(op.reserved_cost_microusd)} · Estimated reported cost: {cost(op.estimated_reported_cost_microusd)}</p>
   {!!op.unpriced_returned_calls&&<p>{op.unpriced_returned_calls} returned calls have no cost estimate.</p>}
   {op.deadline_elapsed&&<p role="status">Recorded deadline elapsed; worker state needs reconciliation. This does not prove that a call is still running.</p>}
  </div>)}
 </article>{!!data.sandbox_operations?.length&&<article className="insight-panel" aria-label="Recorded Docker operations">
  <h4 className="font-semibold">Docker trial operations</h4>
  <p className="text-xs muted">Host-recorded progress for the current phase, not overall campaign completion or proof of container health.</p>
  {data.sandbox_operations.map(op=><div key={op.id} className="mt-3 text-sm">
   <p>{op.family_id} · {op.status} · {op.phase}</p>
   <p className="text-xs muted break-all">Trial {op.id}</p>
   <p>{op.progress.processed==null?'Bar progress unavailable':`${op.progress.processed} / ${op.progress.total??'unknown'} bars observed`}</p>
   <p className="text-xs muted">Last persisted update: {op.updated_at??'Unavailable for legacy trial'}</p>
   {op.suspected_stall&&<p role="status">No persisted update for over 10 minutes. Possible stall; this does not prove worker death or authorize an automatic retry.</p>}
   <details><summary>Recent lifecycle observations</summary>{op.lifecycle.map((event,index)=><p key={index} className="text-xs muted">{event.at} · {event.phase} · {event.event}</p>)}</details>
  </div>)}
 </article>}</>;
}
