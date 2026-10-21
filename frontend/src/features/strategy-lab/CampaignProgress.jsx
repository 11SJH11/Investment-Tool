export default function CampaignProgress({progress}) {
 if(!progress)return null;
 return <article className="insight-panel" aria-label="Recorded research progress">
  <h4 className="font-semibold">Recorded execution: {progress.outcome.replaceAll('_',' ')}</h4>
  <p className="text-xs muted">Baseline/reference jobs and current numeric attempts. Model and Docker work are not included in these counts. Coordinator availability is separate from simulation progress.</p>
  {progress.numeric_trials?.map(trial=><div key={trial.id} className="mt-3 text-sm">
   <p className="break-all">{trial.family_id} · Numeric trial {trial.id} · {trial.status}</p>
   <p className="text-xs muted">{trial.cells.map(cell=>`${cell.role} ${cell.index}, attempt ${cell.attempt}: ${cell.status}`).join(' · ')}</p>
  </div>)}
  <p className="text-sm mt-2">{Object.entries(progress.counts).map(([key,value])=>`${key}: ${value}`).join(' · ')}</p>
  {progress.family_failures.map(f=><p role="alert" key={f.family_id}>{f.family_id}: {f.reason}</p>)}
  {progress.jobs.map(job=><div key={job.id} className="mt-3">
   <p className="text-sm">{job.family_id} · {job.role} · {job.status}</p>
   <p className="text-xs muted break-all">Job {job.id}</p>
   {job.bar_progress_percent!=null&&<><progress aria-label={`${job.role} bars processed`} max="100" value={job.bar_progress_percent} className="w-full"/><p className="text-sm">{job.processed.toLocaleString()} / {job.total.toLocaleString()} bars ({job.bar_progress_percent.toFixed(1)}%)</p></>}
   <p className="text-xs muted">Last persisted queue update: {job.updated_at} UTC</p>
   {job.suspected_stall&&<p role="status">Suspected stall: {progress.stall_explanation}</p>}
   {job.error&&<p role="alert">{job.error}</p>}
  </div>)}
  <p className="text-xs muted mt-3">ETA unavailable. {progress.eta_reason} The campaign wall-time ceiling is a limit, not an ETA.</p>
 </article>;
}
