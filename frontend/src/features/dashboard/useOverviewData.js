import {useEffect,useState} from 'react';
import {api} from '../../api/client';
import {journalToday} from '../journal/journalUtils';
export function useOverviewData() {
  const [data,setData]=useState({}),[errors,setErrors]=useState([]);
  useEffect(()=>{let active=true;const load=async()=>{
    const settings=await api.journalSettings().catch(()=>({timezone:'UTC'}));const today=journalToday(settings.timezone||'UTC');const start=new Date(today+'T12:00:00Z');start.setUTCDate(start.getUTCDate()-29);
    const tasks=[['journal',()=>api.journalReport({timezone:settings.timezone||'UTC',date_from:start.toISOString().slice(0,10),date_to:today})],['accounts',()=>api.brokerPortfolioAccounts()],['jobs',()=>api.backtestJobs()],['runs',()=>api.strategyLabRuns(10)]];
    const results=await Promise.allSettled(tasks.map(([,fn])=>fn()));if(!active)return;
    setData(old=>({...old,...Object.fromEntries(results.flatMap((r,i)=>r.status==='fulfilled'?[[tasks[i][0],r.value]]:[])),period:`${start.toISOString().slice(0,10)} to ${today}`}));setErrors(results.flatMap((r,i)=>r.status==='rejected'?[`${tasks[i][0]} is currently unavailable`]:[]));
  };load();const timer=setInterval(load,30000);return()=>{active=false;clearInterval(timer);};},[]);return {data,errors};
}
