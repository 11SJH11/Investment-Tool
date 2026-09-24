import {useEffect,useRef,useState} from 'react';
import {api} from '../../api/client.js';
import {serializeScan} from './scanModel.js';

const ACTIVE=new Set(['queued','running']);

export function useScan() {
 const [result,setResult]=useState({items:[],total:0,coverage:{}}),[loading,setLoading]=useState(false),[error,setError]=useState(''),[job,setJob]=useState(null);
 const generation=useRef(0),lastQuery=useRef(null),lastStatus=useRef('idle');
 useEffect(()=>()=>{generation.current++;},[]);
 const run=async (query,{quiet=false}={})=>{
   const id=++generation.current;lastQuery.current=query;if(!quiet)setLoading(true);setError('');
   try{
     const request=serializeScan(query);let all=[],response;
     do{
       response=await api.scan({...request,offset:all.length,limit:5000});
       if(id!==generation.current)return;
       all.push(...response.items);if(!response.items.length)break;
     }while(all.length<response.total);
     setResult({...response,items:all.map(r=>({...r,id:r.ticker}))});setJob(response.job);
   }catch(e){if(id===generation.current)setError(e.message);}
   finally{if(id===generation.current&&!quiet)setLoading(false);}
 };
 const refresh=async()=>{try{setJob(await api.refreshTechnicals());setError('');}catch(e){setError(e.message);}};
 useEffect(()=>{
   const status=job?.status||'idle',wasActive=ACTIVE.has(lastStatus.current);lastStatus.current=status;
   if(ACTIVE.has(status)){
     const timer=setTimeout(()=>api.technicalStatus().then(setJob).catch(e=>setError(e.message)),1000);
     return()=>clearTimeout(timer);
   }
   if(wasActive&&status==='completed'&&lastQuery.current)run(lastQuery.current,{quiet:true});
 },[job?.status,job?.processed,job?.phase]);
 return {result,loading,error,setError,run,refresh,job};
}
