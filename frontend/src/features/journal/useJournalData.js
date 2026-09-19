import {useEffect,useState} from 'react';
import {api} from '../../api/client.js';
export function useJournalData(filters,revision,enabled=true) {
  const [report,setReport]=useState(null),[loading,setLoading]=useState(true),[error,setError]=useState('');
  const query=JSON.stringify(filters);
  useEffect(()=>{if(!enabled)return;let active=true;setLoading(true);setError('');api.journalReport(JSON.parse(query)).then(r=>{if(active)setReport(r);}).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[query,revision,enabled]);
  return {report,loading,error};
}
