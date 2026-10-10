import {useState} from 'react';
import {api} from '../../api/client';

export default function FuturesDiagnosticsPanel(){
  const [symbol,setSymbol]=useState('NQ1!'),[timeframe,setTimeframe]=useState('1m');
  const [start,setStart]=useState(''),[end,setEnd]=useState(''),[busy,setBusy]=useState(false),[result,setResult]=useState(null),[error,setError]=useState('');
  const run=async compare=>{setBusy(true);setError('');setResult(null);try{setResult(await api.futuresDiagnostics({symbol,timeframe,start:start+'T00:00:00Z',end:end+'T00:00:00Z',compare}));}catch(e){setError(e.message);}finally{setBusy(false);}};
  return <section className="mt-5 rounded-xl border p-4">
    <h3 className="font-semibold">Futures provider diagnostics</h3>
    <p className="muted text-xs mt-2">Explicit read-only requests through the local cache. MT5 needs a configured local terminal with genuine CME contracts. This does not change the preferred provider. Dates are UTC; end is exclusive. Maximum 31 days per comparison.</p>
    <div className="ui-toolbar mt-3">
      <label>Contract <input className="input w-36" value={symbol} onChange={e=>setSymbol(e.target.value)} placeholder="NQ1! or NQZ26"/></label>
      <label>Timeframe <select className="input" value={timeframe} onChange={e=>setTimeframe(e.target.value)}>{['1m','5m','15m','30m','1h','4h','1d'].map(t=><option key={t}>{t}</option>)}</select></label>
      <label>From <input className="input" type="date" value={start} onChange={e=>setStart(e.target.value)}/></label>
      <label>Until <input className="input" type="date" value={end} onChange={e=>setEnd(e.target.value)}/></label>
      <button className="mini-btn" disabled={busy||!start||!end} onClick={()=>run(false)}>Test MT5 history</button>
      <button className="mini-btn" disabled={busy||!start||!end} onClick={()=>run(true)}>{busy?'Checking...':'Compare Massive / MT5'}</button>
    </div>
    {error&&<p role="alert" className="text-sm mt-3">{error}</p>}
    {result&&<div role="status" className="mt-3 space-y-3">
      {Object.entries(result.providers).map(([name,p])=><div key={name}><strong>{name.toUpperCase()}: {p.status}</strong>{p.status==='connected'?<p className="text-xs">{p.bars} bars / First {p.first_bar} / Latest {p.latest_bar} / First request {p.first_request_seconds}s / Cached {p.cached_request_seconds}s / {p.gap_intervals} gap intervals</p>:<p className="text-xs">{p.message}</p>}</div>)}
      <p className="muted text-xs">{result.note}</p>
      <details><summary>Contract, gap and price comparison details</summary><pre className="overflow-auto max-h-80 text-xs whitespace-pre-wrap break-all">{JSON.stringify(result,null,2)}</pre></details>
    </div>}
  </section>;
}
