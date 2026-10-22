const cost=value=>value==null?'Unknown':`$${(value/1000000).toFixed(4)}`;
export default function CampaignOperations({data}){
 if(!data?.model_operations?.length)return null;
 return <article className="insight-panel" aria-label="Recorded model operations">
  <h4 className="font-semibold">Model operations</h4>
  <p className="text-xs muted">{data.limitation}</p>
  {data.model_operations.map(op=><div key={op.id} className="mt-3 text-sm">
   <p>{op.family_id} · {op.kind} · {op.status}</p>
   <p className="text-xs muted break-all">Operation {op.id}</p>
   {op.operation.role&&<p>{op.operation.role}: {op.operation.status} · {op.elapsed_seconds==null?'Duration unavailable':`${Math.floor(op.elapsed_seconds)} seconds elapsed`}</p>}
   <p>Calls reserved: {op.reserved_calls??'Unknown'} · Returned usage: {op.returned_usage_calls}</p>
   <p>Cost reserved: {cost(op.reserved_cost_microusd)} · Estimated reported cost: {cost(op.estimated_reported_cost_microusd)}</p>
   {!!op.unpriced_returned_calls&&<p>{op.unpriced_returned_calls} returned calls have no cost estimate.</p>}
   {op.deadline_elapsed&&<p role="status">Recorded deadline elapsed; worker state needs reconciliation. This does not prove that a call is still running.</p>}
  </div>)}
 </article>;
}
