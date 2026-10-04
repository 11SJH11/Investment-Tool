import {useCallback,useEffect,useRef,useState} from 'react';
import TradeAuditChart from './TradeAuditChart.jsx';
import PerformanceChart from './PerformanceChart.jsx';
import {exportScope,researchRow,tradeReference} from './reviewNavigation.js';
import {ResearchPdf,evidenceLines,documentFields} from './researchPdf.js';
import {toCsv,safeFilename} from '../../utils/csv.js';

export default function ResearchPack({run,filtered,selected}) {
  const [scope,setScope]=useState('filtered'),[exit,setExit]=useState(true),[active,setActive]=useState(null),[progress,setProgress]=useState(''),[busy,setBusy]=useState(false),[files,setFiles]=useState([]),[error,setError]=useState('');
  const pending=useRef(null),cancelled=useRef(false),urls=useRef([]),mounted=useRef(true);
  const ready=useCallback(value=>pending.current?.(value),[]);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;cancelled.current=true;pending.current?.({cancelled:true});urls.current.forEach(URL.revokeObjectURL);}},[]);
  const release=()=>{urls.current.forEach(URL.revokeObjectURL);urls.current=[];setFiles([]);};
  const publish=(blob,name)=>{const url=URL.createObjectURL(blob);urls.current.push(url);setFiles(old=>[...old,{name,url,size:blob.size}]);};
  const capture=task=>new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.current=null;reject(new Error('Chart rendering timed out. Retry the export; completed parts remain available.'));},120000);pending.current=value=>{clearTimeout(timer);pending.current=null;resolve(value)};setActive(task);});
  const cancel=()=>{cancelled.current=true;pending.current?.({cancelled:true});};
  const start=async()=>{
    if(busy)return;
    const entries=exportScope(run.trades||[],filtered,selected,scope);if(!entries.length)return;
    release();setBusy(true);setError('');cancelled.current=false;const rows=[];let completed=0;
    try{
      setProgress('Rendering full-run equity and drawdown overview...');
      const overview=(run.equity_curve||[]).length?await capture({kind:'overview'}):null;
      if(cancelled.current)return;
      for(let offset=0;offset<entries.length;offset+=50){
        const pdf=new ResearchPdf();const title=`Run ${run.saved_run.id} / ${run.saved_run.name||run.strategy?.name||'Backtest'}`;
        pdf.page(title,[`Full-run overview. Export scope: ${scope}; ${entries.length} trades. UTC source timestamps; charts America/New_York.`,...documentFields({metrics:run.metrics,strategy:run.strategy,config:run.config,symbols:run.symbols,timeframe:run.primary_timeframe,session:run.session})]);
        if(overview?.data)pdf.page(title+' / Equity and drawdown',['Entire saved curve; filtered trades do not recompute portfolio performance.'],overview);
        else pdf.page(title+' / Equity and drawdown',['No saved equity observations.']);
        const chunk=entries.slice(offset,offset+50);
        for(const {trade,index} of chunk){
          if(cancelled.current)break;
          setProgress(`Building Research Pack: ${completed} / ${entries.length} trades. Rendering #${index+1}...`);
          const data=await capture({kind:'trade',trade,index,exit});if(cancelled.current)break;
          const ref=tradeReference(run.saved_run.id,index);
          const row=researchRow(run,trade,index,data.review);if(data.warning)row.review_warnings+='; '+data.warning;rows.push(row);
          const facts=[`${trade.symbol} / ${trade.direction} / Entry ${trade.entry_time} @ ${trade.entry_price} / Exit ${trade.exit_time} @ ${trade.exit_price}`,`P&L ${trade.net_pnl} / Return ${trade.pnl_pct==null?'Not recorded':trade.pnl_pct+'%'} / R ${trade.r_multiple??'Not recorded'} / ${row.duration_minutes} minutes / ${trade.exit_reason}`,`Reopen: saved Runs > Run ${run.saved_run.id} > Trades > Jump to trade #${index+1}.`];
          const images=data.images||[];
          pdf.page(ref+' / Full context',facts,images.find(i=>i.kind==='full'));
          for(const image of images.filter(i=>i.kind!=='full'))pdf.page(ref+' / '+image.kind+' detail',facts.slice(0,2),image);
          pdf.page(ref+' / Strategy evidence',[...evidenceLines(data.review||{}),...(data.warning?['Warning: '+data.warning]:[]),'Volume is research context unless declared as strategy evidence.','Recorded trade metadata:',...documentFields(trade.metadata||{})]);
          completed++;
          setProgress(`Building Research Pack: ${completed} / ${entries.length} trades rendered`);
          setActive(null);await new Promise(resolve=>setTimeout(resolve,0));
        }
        if(cancelled.current)break;
        publish(pdf.blob(),safeFilename(`run-${run.saved_run.id}-trade-review-pack-${offset+1}-${offset+chunk.length}.pdf`));
      }
      if(!cancelled.current){publish(new Blob(['\ufeff'+toCsv(rows)],{type:'text/csv;charset=utf-8'}),`run-${run.saved_run.id}-trade-review-data.csv`);setProgress(`Research Pack ready: ${completed} trades. Download the files below.`);}
    }catch(e){if(mounted.current){setError(e.message);setProgress(`Export failed after ${completed} trades. Completed PDF parts remain available.`);}}
    finally{pending.current=null;if(mounted.current){setActive(null);setBusy(false);if(cancelled.current)setProgress(`Cancelled after ${completed} trades. Only completed PDF parts are retained; no complete CSV was produced.`);}}
  };
  const count=exportScope(run.trades||[],filtered,selected,scope).length;
  return <section className="ui-section" aria-label="Research Pack export"><div className="ui-toolbar"><strong>Trade Review Research Pack</strong><select aria-label="Export scope" className="input" disabled={busy} value={scope} onChange={e=>setScope(e.target.value)}><option value="all">All trades</option><option value="filtered">Current filters / order</option><option value="selected">Selected trades</option></select><label><input type="checkbox" checked={exit} disabled={busy} onChange={e=>setExit(e.target.checked)}/> Exit detail</label><button className="mini-btn" disabled={busy||!count||!run.saved_run?.id} onClick={start}>Export research pack ({count})</button>{busy&&<button className="mini-btn" onClick={cancel}>Cancel export</button>}</div><p className="text-xs muted">PDF + CSV. Full chart, entry detail, strategy evidence and full-run equity included. Up to 50 trades per PDF. Keep this viewer open while rendering. Historical/extended indicators may require provider data; missing evidence is labelled.</p><p role="status">{progress}</p>{error&&<p role="alert">{error}</p>}<div className="ui-toolbar">{files.map(file=><a className="mini-btn" key={file.name} href={file.url} download={file.name}>{file.name} ({(file.size/1048576).toFixed(1)} MB)</a>)}</div>
    {active&&<div aria-hidden="true" inert style={{position:'fixed',left:-20000,top:0,width:1600,pointerEvents:'none'}}>{active.kind==='overview'?<PerformanceChart points={run.equity_curve} startingBalance={run.metrics?.starting_balance} onCapture={ready}/>:<TradeAuditChart key={active.index} run={run} tradeIndex={active.index} trade={active.trade} timeframe={run.primary_timeframe} session={run.session} capture={{exit:active.exit,done:ready}}/>}</div>}
  </section>;
}
