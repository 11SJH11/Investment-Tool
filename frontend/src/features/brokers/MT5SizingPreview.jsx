import {useState} from 'react';
import {api} from '../../api/client';

export default function MT5SizingPreview({profile,symbol,disabled}) {
  const [values,setValues]=useState({side:'buy',entry:'',stop:'',risk_amount:''});
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[result,setResult]=useState(null);
  const change=(key,value)=>{setValues(v=>({...v,[key]:value}));setResult(null);setError('');};
  const calculate=async e=>{
    e.preventDefault();setBusy(true);setResult(null);setError('');
    try {setResult(await api.brokerSizingPreview(profile.profile_id,{symbol,side:values.side,
      entry:Number(values.entry),stop:Number(values.stop),risk_amount:Number(values.risk_amount)}));}
    catch(e){setError(e.message);}finally{setBusy(false);}
  };
  return <details className="my-3"><summary>Broker sizing estimate · read-only</summary>
    <p className="text-xs">Uses current account currency and broker specifications at your supplied prices. This does not place or authorize an order.</p>
    <form className="ui-toolbar mt-2" onSubmit={calculate}>
      <label>Side <select className="input" disabled={busy} value={values.side} onChange={e=>change('side',e.target.value)}><option value="buy">Buy</option><option value="sell">Sell</option></select></label>
      {[['entry','Entry price'],['stop','Stop price'],['risk_amount','Target risk (account currency)']].map(([key,label])=><label key={key}>{label}<input className="input" type="number" step="any" min="0" required disabled={busy} value={values[key]} onChange={e=>change(key,e.target.value)}/></label>)}
      <button className="mini-btn" disabled={busy||disabled||!profile.configured}>{busy?'Calculating…':'Calculate estimate'}</button>
    </form>
    {error&&<p role="alert">{error}</p>}
    {result&&<section aria-label="Broker sizing result" className="text-xs mt-2">
      <p>{result.environment} · {result.symbol} · {result.currency} · observed {new Date(result.observed_at).toLocaleString()}</p>
      <p>Lots: {result.quantity_lots} · Target risk: {result.target_risk} · Estimated stop loss: {result.actual_estimated_risk}</p>
      <p>Estimated margin: {result.estimated_margin} · Free margin: {result.free_margin} · Equity: {result.equity}</p>
      {result.rejection_reason&&<p role="alert">Cannot use this estimate: {result.rejection_reason.replaceAll('_',' ')}</p>}
      {result.warnings.map(w=><p key={w}>{w}</p>)}
    </section>}
  </details>;
}
