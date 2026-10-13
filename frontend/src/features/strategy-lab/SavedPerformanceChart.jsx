import {useEffect,useState} from 'react';
import PerformanceChart from './PerformanceChart.jsx';
import {api} from '../../api/client.js';
import {createSectionCache} from './runSections.js';

const sections=createSectionCache((id,section)=>api.strategyLabRunSection(id,section),3,60000);
export default function SavedPerformanceChart({runId,points,...props}){
 const [data,setData]=useState(null),[error,setError]=useState(''),[full,setFull]=useState(false),[retry,setRetry]=useState(0);
 useEffect(()=>{
  if(points||!runId)return;
  let active=true;setData(null);setError('');
  const timer=setTimeout(()=>sections.get(runId,full?'performance-full':'performance').then(value=>{if(active)setData(value.result)}).catch(e=>{if(active)setError(e.message)}),0);
  return()=>{active=false;clearTimeout(timer)};
 },[runId,points,full,retry]);
 if(points)return <PerformanceChart points={points} {...props}/>;
 if(error)return <p role="alert">{error} <button className="mini-btn" onClick={()=>setRetry(x=>x+1)}>Retry performance</button></p>;
 if(!data)return <p role="status">Loading performance...</p>;
 return <><p className="text-xs muted">{full?'Full saved chart detail.':`Display projection: ${data.display_projection?.display_points??0} of ${data.display_projection?.source_points??0} observations. Bucket extrema and trade events retained; metrics use all observations.`}</p>
 {!full&&<button className="mini-btn" onClick={()=>setFull(true)}>Load full chart detail for zoom (may be slow)</button>}
 <PerformanceChart points={data.equity_curve||[]} projected={!full} {...props}/></>;
}
