import {useRef,useState} from 'react';
import {api} from '../../api/client';
import DataTable from '../../components/table/DataTable.jsx';
import MT5HistoryPanel from './MT5HistoryPanel.jsx';

const columns = [
  {key:'name',label:'Broker symbol'}, {key:'description',label:'Description'},
  {key:'instrument_type',label:'Type',kind:'category'},
  {key:'trade_tick_size',label:'Tick size',kind:'number'},
  {key:'trade_tick_value',label:'Tick value',kind:'number'},
  {key:'trade_contract_size',label:'Contract size',kind:'number'},
  {key:'currency_profit',label:'Profit currency'},
];

export default function MT5SymbolCatalog({profile,disabled}) {
  const [catalog,setCatalog]=useState(null),[search,setSearch]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[detail,setDetail]=useState(null);
  const activeRequest=useRef(0);
  const load=async(refresh=false,offset=0)=>{
    const request=++activeRequest.current;
    setBusy(true);setError('');setDetail(null);
    try {
      if(refresh)await api.refreshBrokerSymbols(profile.profile_id);
      const result=await api.brokerSymbols(profile.profile_id,search,offset);
      if(request===activeRequest.current)setCatalog(result);
    }catch(e){if(request===activeRequest.current)setError(e.message);}
    finally{if(request===activeRequest.current)setBusy(false);}
  };
  return <details className="mt-3"><summary>MT5 broker instruments</summary>
    <p className="text-xs mt-2">Current broker metadata, not historical specifications. Broker CFDs are not CME futures. Missing values remain unknown; discovery does not prove historical data coverage.</p>
    {!profile.account_key&&<p>Test the connection and select an account first.</p>}
    <form className="ui-toolbar mt-2" onSubmit={e=>{e.preventDefault();load();}}>
      <input className="input" aria-label="Search MT5 catalog" placeholder="Symbol, description or type" value={search} onChange={e=>setSearch(e.target.value)}/>
      <button className="mini-btn" disabled={disabled||busy||!profile.account_key}>Search saved catalog</button>
      <button className="mini-btn" type="button" disabled={disabled||busy||!profile.configured||!profile.account_key} onClick={()=>load(true)}>Refresh from terminal</button>
    </form>
    {busy&&<p role="status">Loading instruments…</p>}
    {error&&<p role="alert">{error}</p>}
    {catalog&&<>
      <p className="text-xs mt-2">{catalog.total} matching / {catalog.catalog_total} instruments. Observed: {catalog.observed_at?new Date(catalog.observed_at).toLocaleString():'Not discovered'}. Table filters apply to this page.</p>
      <DataTable id={`mt5-catalog-${profile.account_key}`} label="MT5 instruments" columns={columns} rows={catalog.items.map(row=>({...row,id:row.instrument_id}))} primaryAction={{label:'Metadata',onClick:setDetail}}/>
      <div className="ui-toolbar"><button className="mini-btn" disabled={busy||!catalog.offset} onClick={()=>load(false,Math.max(0,catalog.offset-100))}>Previous 100</button>
        <button className="mini-btn" disabled={busy||catalog.offset+100>=catalog.total} onClick={()=>load(false,catalog.offset+100)}>Next 100</button></div>
    </>}
    {detail&&<section aria-label="Broker symbol metadata" className="mt-3"><h4>{detail.name} metadata</h4>
      <MT5HistoryPanel key={detail.instrument_id} profile={profile} symbol={detail.name} disabled={disabled}/>
      <dl className="grid grid-cols-2 gap-2 text-xs">{Object.entries(detail).filter(([key])=>key!=='id').map(([key,value])=><div key={key} className="min-w-0 break-words"><dt>{key.replaceAll('_',' ')}</dt><dd>{value==null?'Unknown':String(value)}</dd></div>)}</dl>
    </section>}
  </details>;
}
