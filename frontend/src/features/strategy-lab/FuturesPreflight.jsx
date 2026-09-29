import {useState} from 'react';
import {api} from '../../api/client';
export default function FuturesPreflight({buildPayload}) {
  const [report,setReport]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const check=async()=>{setBusy(true);setError('');setReport(null);try{setReport(await api.futuresPreflight(buildPayload()));}catch(e){setError(e.message);}finally{setBusy(false);}};
  return <details className="mt-3"><summary>Futures data & sizing preflight</summary><p className="text-xs my-2">Checks one futures symbol’s raw execution data before simulation. May load data into the existing local cache. No exchange/broker margin is assumed.</p><button className="mini-btn" disabled={busy} onClick={check}>{busy?'Checking data…':'Check futures configuration'}</button>{error&&<p role="alert">{error}</p>}{report&&<div className="text-xs space-y-2 mt-3"><strong>{report.ready?'Data checks passed; signal-specific sizing still applies':report.reason}</strong><dl className="grid gap-2 sm:grid-cols-2">{Object.entries(report).filter(([k])=>!['reason','ready','warnings','limitations'].includes(k)).map(([k,v])=><div key={k}><dt>{k.replaceAll('_',' ')}</dt><dd>{Array.isArray(v)?v.join(', '):String(v)}</dd></div>)}</dl>{[...report.warnings,...report.limitations].map(t=><p key={t}>{t}</p>)}</div>}</details>;
}
