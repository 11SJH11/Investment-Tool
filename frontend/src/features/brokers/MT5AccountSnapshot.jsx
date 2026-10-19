import {useState} from 'react';
import {api} from '../../api/client';
import DataTable from '../../components/table/DataTable.jsx';

const columns=[{key:'symbol',label:'Broker symbol'},{key:'ticket',label:'Ticket'},
  {key:'type',label:'MT5 type'},{key:'volume',label:'Lots',kind:'number'},
  {key:'price_open',label:'Open price',kind:'number'},{key:'sl',label:'Stop',kind:'number'},
  {key:'tp',label:'Target',kind:'number'},{key:'profit',label:'Open P&L',kind:'number'}];
export default function MT5AccountSnapshot({profile,disabled}) {
  const [snapshot,setSnapshot]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  async function refresh(){
    setBusy(true);setError('');
    try{setSnapshot(await api.brokerAccountSnapshot(profile.profile_id));}
    catch(e){setError(e.message);}finally{setBusy(false);}
  }
  return <details className="mt-3"><summary>Account, positions and pending orders · read-only</summary>
    <button className="mini-btn mt-2" disabled={busy||disabled||!profile.configured||!profile.account_key} onClick={refresh}>{busy?'Reading account…':'Refresh account snapshot'}</button>
    {error&&<p role="alert">{error}{snapshot?' Displaying the previous snapshot; it may be stale.':''}</p>}
    {snapshot&&<div className="mt-2 text-xs">
      <p>{snapshot.environment} · {snapshot.account.currency} · Observed {new Date(snapshot.observed_at).toLocaleString()}</p>
      <p>Balance {snapshot.account.balance} · Equity {snapshot.account.equity} · Margin {snapshot.account.margin} · Free margin {snapshot.account.margin_free}</p>
      <p>{snapshot.warning}</p>
      <DataTable id={`mt5-open-${profile.account_key}`} label="MT5 open positions" columns={columns} rows={snapshot.positions.map(p=>({...p,id:p.ticket,type:p.type===0?'BUY':p.type===1?'SELL':`Unknown (${p.type})`}))}/>
      <DataTable id={`mt5-pending-${profile.account_key}`} label="MT5 pending orders" columns={columns.filter(c=>c.key!=='profit')} rows={snapshot.pending_orders.map(o=>({...o,id:o.ticket,volume:o.volume_current,type:({2:'BUY LIMIT',3:'SELL LIMIT',4:'BUY STOP',5:'SELL STOP',6:'BUY STOP LIMIT',7:'SELL STOP LIMIT'})[o.type]||`Unknown (${o.type})`}))}/>
    </div>}
  </details>;
}
