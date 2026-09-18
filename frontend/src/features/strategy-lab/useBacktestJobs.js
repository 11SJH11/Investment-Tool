import {useCallback, useEffect, useRef, useState} from 'react';
import {api} from '../../api/client';
import {configurationError} from './backtest-workflow.js';

export default function useBacktestJobs(onComplete) {
  const [jobs,setJobs]=useState([]),[workers,setWorkers]=useState(2),[error,setError]=useState('');
  const completed=useRef(''), pending=useRef(null);
  const refresh=useCallback(async()=>{
    try {
      const data=await api.backtestJobs();setJobs(data.jobs);setWorkers(data.max_workers);setError('');
      const signature=data.jobs.filter(j=>j.status==='completed').map(j=>j.id).join(',');
      if(signature!==completed.current){completed.current=signature;onComplete?.();}
    } catch(e){setError(e.message);}
  },[onComplete]);
  useEffect(()=>{let stopped=false,timer;const poll=async()=>{await refresh();if(!stopped)timer=setTimeout(poll,1000);};poll();return()=>{stopped=true;clearTimeout(timer);};},[refresh]);
  const submit=async runs=>{
    if(!runs.length)throw new Error('Choose at least one symbol.');
    const invalid=runs.map(configurationError).find(Boolean);
    if(invalid)throw new Error(invalid);
    // Keep the key after an ambiguous network failure. A manual retry of the
    // same submission cannot duplicate jobs already accepted by the server.
    const signature=JSON.stringify(runs);
    if(pending.current?.signature!==signature)pending.current={signature,key:crypto.randomUUID()};
    await api.queueBacktests(runs,pending.current.key);pending.current=null;await refresh();
  };
  const cancel=async id=>{await api.cancelBacktestJob(id);await refresh();};
  const retry=async id=>{await api.retryBacktestJob(id,crypto.randomUUID());await refresh();};
  return {jobs,workers,error,submit,cancel,retry,refresh};
}
