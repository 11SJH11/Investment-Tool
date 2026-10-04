import {notifyActivity} from '../../app/activityEvents.js';
import {useCallback, useEffect, useRef, useState} from 'react';
import {api} from '../../api/client';
import {jobStatus} from './researchPolling.js';
import {configurationError} from './backtest-workflow.js';

export default function useBacktestJobs(onComplete) {
  const [jobs,setJobs]=useState([]),[workers,setWorkers]=useState(2),[error,setError]=useState('');
  const [compute,setCompute]=useState(null);
  const completed=useRef(''), pending=useRef(null), callback=useRef(onComplete);callback.current=onComplete;
  const refresh=useCallback(()=>jobStatus.refresh(),[]);
  useEffect(()=>jobStatus.subscribe((data,failure)=>{
    if(failure){setError(failure.message);return;}
    if(!data)return;
    setJobs(data.jobs);setWorkers(data.max_workers);setCompute(data.compute||null);setError('');
    const signature=data.jobs.filter(j=>j.status==='completed').map(j=>j.id).join(',');
    if(signature!==completed.current){completed.current=signature;callback.current?.();}
  }),[]);
  const submit=async runs=>{
    if(!runs.length)throw new Error('Choose at least one symbol.');
    const invalid=runs.map(configurationError).find(Boolean);
    if(invalid)throw new Error(invalid);
    // Keep the key after an ambiguous network failure. A manual retry of the
    // same submission cannot duplicate jobs already accepted by the server.
    const signature=JSON.stringify(runs);
    if(pending.current?.signature!==signature)pending.current={signature,key:crypto.randomUUID()};
    await api.queueBacktests(runs,pending.current.key);pending.current=null;notifyActivity({title:'Backtests queued',detail:`${runs.length} independent run(s). Continue working; results open only when you choose.`});await refresh();
  };
  const cancel=async id=>{await api.cancelBacktestJob(id);await refresh();};
  const retry=async id=>{await api.retryBacktestJob(id,crypto.randomUUID());await refresh();};
  const remove=async id=>{await api.deleteBacktestJob(id);await refresh();};
  const clearFinished=async()=>{await api.clearFinishedBacktestJobs();await refresh();};
  return {jobs,workers,compute,error,submit,cancel,retry,remove,clearFinished,refresh};
}
