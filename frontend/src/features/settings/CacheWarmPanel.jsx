import {useEffect,useState} from 'react';
import {api} from '../../api/client.js';
import {warmActive,warmRange,warmRequest,canResume} from './warmupView.js';

export default function CacheWarmPanel({symbols,days,onDaysChange,onComplete}) {
  const [jobs,setJobs]=useState([]), [error,setError]=useState(''), [busy,setBusy]=useState(false);
  const refresh=()=>api.marketCacheWarmJobs().then(result=>setJobs(result.items||[]));
  useEffect(()=>{let live=true;api.marketCacheWarmJobs().then(result=>{if(live)setJobs(result.items||[])}).catch(e=>{if(live)setError(e.message)});return()=>{live=false}},[]);
  const polling=jobs.some(warmActive)||jobs.some(j=>j.retry_at&&!canResume(j));
  useEffect(()=>{
    if(!polling)return;
    let live=true,timer;
    const poll=async()=>{try{const result=await api.marketCacheWarmJobs();if(!live)return;setJobs(result.items||[]);if(!(result.items||[]).some(warmActive))onComplete?.();}catch(e){if(live)setError(e.message)}finally{if(live)timer=setTimeout(poll,2000)}};
    timer=setTimeout(poll,2000);return()=>{live=false;clearTimeout(timer)};
  },[polling]);
  const act=async fn=>{setBusy(true);setError('');try{await fn();await refresh()}catch(e){setError(e.message)}finally{setBusy(false)}};
  return <div aria-label="Background history downloads">
    <p className="text-sm font-medium">Persistent favourite history</p>
    <p className="muted text-xs mt-1">Downloads start only when requested. Seven-day chunks yield to waiting Charts, Replay and Backtest requests. A running provider request finishes before pausing. Jobs continue after navigation; interrupted jobs are paused after an app restart.</p>
    <p className="muted text-xs mt-1">The shared cache retains NQ dated contracts and roll provenance. Covered request ranges can include closed sessions and do not guarantee uninterrupted bars. Updates reuse covered history; provider corrections may still require an explicit chart refresh.</p>
    {error&&<p role="alert" className="text-sm text-red-600 mt-2">{error}</p>}
    <div className="ui-toolbar mt-3">
      <label>History window<select className="input" value={days||30} onChange={e=>onDaysChange(Number(e.target.value))}>{[[30,'1 month'],[90,'3 months'],[180,'6 months'],[365,'1 year'],[730,'2 years'],[1825,'5 years']].map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
      <button className="mini-btn" disabled={busy||!symbols.length} onClick={()=>act(()=>api.warmMarketCache(warmRequest(symbols,days||30)))}>Update missing favourite data</button>
      <button className="mini-btn" disabled={busy} onClick={()=>act(()=>api.warmMarketCache(warmRequest(['NQ1!'],days||30)))}>Update missing NQ1! data</button>
      <button className="mini-btn" disabled={busy} onClick={()=>act(refresh)}>Refresh download status</button>
    </div>
    <div className="space-y-3 mt-3">{jobs.map(job=><article key={job.id} className="rounded-lg border border-stone-200 p-3 text-xs" aria-label={`History download ${job.symbols.join(', ')}`}>
      <div className="ui-toolbar"><strong>{job.symbols.join(', ')} | {job.status}</strong><span>{job.chunks_completed||0} chunks persisted | {job.completed}/{job.total} symbols</span>
        {warmActive(job)&&<button className="mini-btn" disabled={busy||job.status==='pausing'} onClick={()=>act(()=>api.controlMarketCacheWarm(job.id,'pause'))}>Pause</button>}
        {['paused','failed'].includes(job.status)&&<button className="mini-btn" disabled={busy||!canResume(job)} onClick={()=>act(()=>api.controlMarketCacheWarm(job.id,'resume'))}>Resume</button>}
      </div>
      <p className="mt-1">Provider: {(job.provider_state||'idle').replaceAll('_',' ')}{job.retry_at?` | Retry after ${warmRange([job.retry_at,job.retry_at]).split(' to ')[0]} UTC`:''}</p>
      {job.current_chunk&&<p>Current chunk: {job.current_chunk.symbol} | {warmRange([job.current_chunk.start,job.current_chunk.end])}</p>}
      {job.items.map(item=><div key={item.symbol} className="mt-2"><strong>{item.symbol}</strong><p>Requested: {warmRange([item.requested_start,item.requested_end])}</p><p>Covered requests: {warmRange(item.downloaded_coverage)}</p></div>)}
      {job.error&&<p role="alert" className="mt-2 text-red-600">{job.error}</p>}
    </article>)}</div>
  </div>;
}
