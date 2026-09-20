import {useEffect,useRef,useState} from 'react';
import {api} from '../../api/client.js';
import {serializeScan} from './scanModel.js';
export function useScan() {
 const [result,setResult]=useState({items:[],total:0,coverage:{}}),[loading,setLoading]=useState(false),[error,setError]=useState(''),[job,setJob]=useState(null);const generation=useRef(0);
 useEffect(()=>()=>{generation.current++;},[]);
 const run=async query=>{const id=++generation.current;setLoading(true);setError('');try{const request=serializeScan(query);let all=[],response;do{response=await api.scan({...request,offset:all.length,limit:500});if(id!==generation.current)return;all.push(...response.items);if(!response.items.length)break;}while(all.length<response.total);setResult({...response,items:all.map(r=>({...r,id:r.ticker}))});setJob(response.job);}catch(e){if(id===generation.current)setError(e.message);}finally{if(id===generation.current)setLoading(false);}};
 const refresh=async()=>{try{setJob(await api.refreshTechnicals());setError('');}catch(e){setError(e.message);}};
 useEffect(()=>{if(!['queued','running'].includes(job?.status))return;const timer=setTimeout(()=>api.technicalStatus().then(setJob).catch(e=>setError(e.message)),1000);return()=>clearTimeout(timer);},[job]);
 return {result,loading,error,setError,run,refresh,job};
}
