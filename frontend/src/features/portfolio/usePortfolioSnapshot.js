import {useEffect,useState} from 'react';
import {api} from '../../api/client';
import {useUIPreference} from '../../app/useUIPreference.js';
export function usePortfolioSnapshot(revision) {
  const [accounts,setAccounts]=useState([]),[account,setAccount]=useUIPreference('portfolio.account',''),[kind,setKind]=useUIPreference('portfolio.kind','position');
  const [data,setData]=useState({items:[],total:0}),[error,setError]=useState(''),[loading,setLoading]=useState(false);
  useEffect(()=>{let active=true;api.brokerPortfolioAccounts().then(r=>{if(active){setAccounts(r.items);if(!r.items.some(a=>a.account_key===account))setAccount(r.items[0]?.account_key||'');}}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[revision]);
  useEffect(()=>{if(!account)return;let active=true;setLoading(true);setError('');(async()=>{let items=[],total=0;do {const page=await api.brokerPortfolioRecords(account,kind,items.length);if(!active)return;total=page.total;items.push(...page.items);if(!page.items.length)break;}while(items.length<total);if(active)setData({items,total});})().catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[account,kind,revision]);
  return {accounts,account,setAccount,kind,setKind,data,error,setError,loading};
}
