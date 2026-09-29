import {useUIPreference} from '../../app/useUIPreference.js';
import {useState} from 'react';
import {Panel,Button,PageToolbar,Section} from '../../components/ui.jsx';
import {queueCounts} from './backtest-workflow.js';
import RunComparison from './RunComparison.jsx';

const ACTIVE=['running','preparing data','preparing shared data','analysing results','saving'];
export default function BacktestJobPanel({queue,onOpen,onOpenExperiment}) {
  const [expanded,setExpanded]=useUIPreference('jobs.expanded',false);
  const [error,setError]=useState(''),[compare,setCompare]=useState([]);
  const action=async fn=>{try{setError('');await fn();}catch(e){setError(e.message);}};
  const groups=Object.groupBy(queue.jobs,j=>j.batch_id);
  return <Panel aria-label="Backtest queue"><PageToolbar><h3 className="font-semibold">Backtest jobs</h3><span className="text-xs">{Object.entries(queueCounts(queue.jobs)).map(([k,v])=>`${v} ${k}`).join(" \u00b7 ")}</span><Button onClick={()=>setExpanded(!expanded)} aria-expanded={expanded}>{expanded?"Collapse jobs":"Show jobs"}</Button>{queue.jobs.some(j=>['completed','failed','cancelled'].includes(j.status))&&<Button onClick={()=>action(()=>queue.clearFinished())}>Clear finished</Button>}<span className="text-xs text-stone-500">Up to {queue.workers} workers · independent capital per symbol</span></PageToolbar>
    {(error||queue.error)&&<p role="alert">{error||queue.error}</p>}
    {!expanded&&queue.jobs.filter(j=>ACTIVE.includes(j.status)).map(j=><p key={j.id} role="status" className="text-xs muted mt-2">{j.payload.run_name||j.payload.symbols.join(", ")} · {j.status}{j.total?` ${j.processed}/${j.total} ${j.payload.research_children?'simulations':'timestamps'} (${Math.floor(100*j.processed/j.total)}%)`:""}</p>)}
    {!queue.jobs.length&&<p className="mt-2 text-sm text-stone-500">Queue a run and keep configuring your next test.</p>}
    <div hidden={!expanded} className="max-h-60 overflow-auto">{Object.entries(groups).map(([id,jobs])=><div key={id} className="ui-section">
      <PageToolbar><span className="text-xs">{Object.entries(queueCounts(jobs)).map(([k,v])=>`${v} ${k}`).join(' · ')}</span>
      {jobs.some(j=>j.status==='queued')&&<Button onClick={()=>action(()=>Promise.all(jobs.filter(j=>j.status==='queued').map(j=>queue.cancel(j.id))))}>Cancel queued</Button>}
      {jobs.filter(j=>j.status==='completed').length>1&&<Button onClick={()=>setCompare(jobs.filter(j=>j.run_id).slice(0,12).map(j=>j.run_id))}>Compare completed</Button>}</PageToolbar>
      {jobs.map(job=><div key={job.id} className="ui-toolbar mt-2 text-xs" data-job-status={job.status}><strong>{job.payload.run_name||job.payload.strategy_key} · {job.payload.symbols.join(', ')}</strong><span role="status">{job.status}{job.total?` · ${job.processed}/${job.total} ${job.payload.research_children?'simulations':'timestamps'} (${Math.floor(100*job.processed/job.total)}%)`:''}{job.cancel_requested&&ACTIVE.includes(job.status)?' · cancellation requested':''}</span>
        {job.payload.research_children?<Button onClick={()=>onOpenExperiment?.(job.payload.experiment_group)}>Open {job.payload.experiment_type} research · {job.payload.research_children.length} simulations</Button>:job.status==='completed'&&<Button onClick={()=>onOpen(job.run_id)}>Open result #{job.run_id}</Button>}
        {['queued',...ACTIVE].includes(job.status)&&<Button disabled={!!job.cancel_requested} onClick={()=>action(()=>queue.cancel(job.id))}>Cancel</Button>}
        {(job.status==='failed'||(job.status==='cancelled'&&job.payload.research_children))&&<><span>{job.error}</span><Button onClick={()=>action(()=>queue.retry(job.id))}>Retry incomplete</Button></>}
        {['completed','failed','cancelled'].includes(job.status)&&<Button onClick={()=>action(()=>queue.remove(job.id))}>Delete job</Button>}
      </div>)}
    </div>)}</div>
    {compare.length>1&&<Section id="queue-comparison" title="Batch comparison"><RunComparison ids={compare}/></Section>}
  </Panel>;
}
