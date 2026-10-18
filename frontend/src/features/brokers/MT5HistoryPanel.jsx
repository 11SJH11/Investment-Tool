import {useState} from 'react';
import {api} from '../../api/client';

export default function MT5HistoryPanel({profile,symbol,disabled}) {
  const [kind,setKind]=useState('1m'),[start,setStart]=useState(''),[end,setEnd]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[result,setResult]=useState(null),[coverage,setCoverage]=useState(null);
  const load=async(download)=>{
    setBusy(true);setError('');
    try {
      if(download){
        const r=await api.brokerMarketHistory(profile.profile_id,{symbol,data_type:kind,start:`${start}:00Z`,end:`${end}:00Z`});
        setResult(r);
      }
      setCoverage(await api.brokerMarketCoverage(profile.profile_id));
    }catch(e){setError(e.message);}finally{setBusy(false);}
  };
  return <details className="my-3"><summary>Historical data and observed coverage</summary>
    <p className="text-xs">Download broker-native history into this Ledger instance. Bars: up to 366 days per request. Ticks: up to one day, 500,000 rows maximum. Exact repeated requests use the local Parquet cache. This does not yet make these datasets selectable in Backtest.</p>
    <form className="ui-toolbar mt-2" onSubmit={e=>{e.preventDefault();load(true);}}>
      <label>Data <select className="input" value={kind} onChange={e=>setKind(e.target.value)}>{['1m','5m','15m','30m','1h','4h','1d','ticks'].map(k=><option key={k}>{k}</option>)}</select></label>
      <label>Start (UTC) <input className="input" type="datetime-local" required value={start} onChange={e=>setStart(e.target.value)}/></label>
      <label>End exclusive (UTC) <input className="input" type="datetime-local" required value={end} onChange={e=>setEnd(e.target.value)}/></label>
      <button className="mini-btn" disabled={busy||disabled||!profile.configured}>Cache history</button>
      <button type="button" className="mini-btn" disabled={busy||disabled} onClick={()=>load(false)}>View cached coverage</button>
    </form>
    {busy&&<p role="status">Reading history…</p>}{error&&<p role="alert">{error}</p>}
    {result&&<p role="status">{result.cache_hit?'Loaded local cache':'Cached provider history'}: {result.rows} records. Tick volume and real volume remain separate.</p>}
    {coverage&&<div className="space-y-2 mt-2">{coverage.items.filter(r=>r.broker_symbol===symbol).map(r=><article className="text-xs break-words" key={`${r.data_type}:${r.requested_start}:${r.requested_end}`}>
      <strong>{r.data_type} · {r.rows} records</strong><p>Observed {r.observed_start} to {r.observed_end}</p>
      <p>Requested {r.requested_start} to {r.requested_end}. Continuous coverage is unverified; missing windows are not filled.</p>
      <p>DOM: {r.dom}. Fingerprint: {r.data_fingerprint}</p>
      <p>Volume: {r.volume_semantics}</p>
      <p>{Object.entries(r.fields||{}).map(([name,counts])=>`${name}: ${counts.non_null_rows}/${r.rows} non-null, ${counts.positive_rows} positive`).join(' · ')}</p>
    </article>)}{!coverage.items.some(r=>r.broker_symbol===symbol)&&<p>No observed cached history for this symbol.</p>}</div>}
  </details>;
}
