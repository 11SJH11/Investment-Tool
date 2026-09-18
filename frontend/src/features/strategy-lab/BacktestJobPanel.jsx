import {useState} from 'react';
import {Panel,Button,PageToolbar,Section} from '../../components/ui.jsx';
import {queueCounts} from './backtest-workflow.js';
import RunComparison from './RunComparison.jsx';

export default function BacktestJobPanel({queue,onOpen}) {
  const [error,setError]=useState(''),[compare,setCompare]=useState([]);
  const action=async fn=>{try{setError('');await fn();}catch(e){setError(e.message);}};
  const groups=Object.groupBy(queue.jobs,j=>j.batch_id);
  return <Panel aria-label="Backtest queue"><PageToolbar><h3 className="font-semibold">Backtest queue</h3><span className="text-xs text-stone-500">Up to {queue.workers} workers · independent capital per symbol</span></PageToolbar>
    {(error||queue.error)&&<p role="alert">{error||queue.error}</p>}
    {!queue.jobs.length&&<p className="mt-2 text-sm text-stone-500">Queue a run and keep configuring your next test.</p>}
    <div className="max-h-80 overflow-auto">{Object.entries(groups).map(([id,jobs])=><div key={id} className="ui-section">
      <PageToolbar><span className="text-xs">{Object.entries(queueCounts(jobs)).map(([k,v])=>`${v} ${k}`).join(' · ')}</span>
      {jobs.some(j=>j.status==='queued')&&<Button onClick={()=>action(()=>Promise.all(jobs.filter(j=>j.status==='queued').map(j=>queue.cancel(j.id))))}>Cancel queued</Button>}
      {jobs.filter(j=>j.status==='completed').length>1&&<Button onClick={()=>setCompare(jobs.filter(j=>j.run_id).slice(0,12).map(j=>j.run_id))}>Compare completed</Button>}</PageToolbar>
      {jobs.map(job=><div key={job.id} className="ui-toolbar mt-2 text-xs" data-job-status={job.status}><strong>{job.payload.run_name||job.payload.strategy_key} · {job.payload.symbols.join(', ')}</strong><span role="status">{job.status}{job.total?` · ${job.processed}/${job.total} timestamps (${Math.floor(100*job.processed/job.total)}%)`:''}{job.cancel_requested&&['running','preparing data'].includes(job.status)?' · cancellation requested':''}</span>
        {job.status==='completed'&&<Button onClick={()=>onOpen(job.run_id)}>Open result #{job.run_id}</Button>}
        {['queued','running','preparing data'].includes(job.status)&&<Button disabled={!!job.cancel_requested} onClick={()=>action(()=>queue.cancel(job.id))}>Cancel</Button>}
        {job.status==='failed'&&<><span>{job.error}</span><Button onClick={()=>action(()=>queue.retry(job.id))}>Retry failed</Button></>}
      </div>)}
    </div>)}</div>
    {compare.length>1&&<Section id="queue-comparison" title="Batch comparison"><RunComparison ids={compare}/></Section>}
  </Panel>;
}
