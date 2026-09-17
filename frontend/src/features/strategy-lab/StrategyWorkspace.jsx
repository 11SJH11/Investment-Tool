import {useEffect, useRef, useState} from 'react';
import {api} from '../../api/client';
import {pythonTokens} from './workspace-utils';

const colours={plain:'#e2e8f0',keyword:'#c4b5fd',string:'#86efac',comment:'#94a3b8',number:'#fcd34d'};
const defaults={strategy_key:'workspace_my_strategy',symbols:['AAPL'],start_date:'2026-01-05',end_date:'2026-01-09',primary_timeframe:'5m',session:'regular',starting_balance:10000,sizing_mode:'risk_pct',risk_value:1,commission_per_order:0,slippage_bps:0,spread_bps:0,save_run:true};

export default function StrategyWorkspace({onResult,onDirtyChange}) {
  const [files,setFiles]=useState([]),[filename,setFilename]=useState('_workspace_my_strategy.py');
  const [source,setSource]=useState(''),[savedSource,setSavedSource]=useState(''),[savedFilename,setSavedFilename]=useState('');
  const [revision,setRevision]=useState(null),[readOnly,setReadOnly]=useState(false),[trusted,setTrusted]=useState(false);
  const [busy,setBusy]=useState(false),[report,setReport]=useState(null),[error,setError]=useState('');
  const [settings,setSettings]=useState(JSON.stringify(defaults,null,2));
  const original=useRef(''),pre=useRef(null),editor=useRef(null);
  const dirty=source!==savedSource||filename!==savedFilename;
  useEffect(()=>{onDirtyChange?.(dirty||busy);return()=>onDirtyChange?.(false);},[dirty,busy,onDirtyChange]);
  const refresh=()=>api.workspaceFiles().then(data=>{setFiles(data.files);original.current=data.template;return data;});
  useEffect(()=>{let active=true;api.workspaceFiles().then(data=>{if(!active)return;setFiles(data.files);original.current=data.template;setSource(data.template);setSavedSource(data.template);setSavedFilename(data.default_filename);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[]);
  useEffect(()=>{const guard=e=>{if(dirty){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',guard);return()=>window.removeEventListener('beforeunload',guard);},[dirty]);
  const replace=()=>!dirty||window.confirm('Discard the unsaved workspace changes?');
  const load=async name=>{if(!name||!replace())return;setBusy(true);setError('');try{const data=await api.workspaceRead(name);setFilename(name);setSavedFilename(name);setSource(data.source);setSavedSource(data.source);setRevision(data.revision);setReadOnly(data.read_only);setTrusted(false);setReport(null);}catch(e){setError(e.message);}finally{setBusy(false);}};
  const fresh=()=>{if(!replace())return;setFilename('_workspace_my_strategy.py');setSavedFilename('');setSource(original.current);setRevision(null);setReadOnly(false);setTrusted(false);setReport(null);};
  const copy=()=>{setFilename('_workspace_copy.py');setRevision(null);setReadOnly(false);setTrusted(false);setReport({message:'Copy created in the editor. Set StrategySpec.key to workspace_copy (or match your new filename) before executing.'});};
  const action=async kind=>{setBusy(true);setError('');setReport(null);try{
    const draft={filename,source,expected_revision:filename===savedFilename?revision:null,trusted};
    const response=kind==='save'?await api.workspaceSave(draft):kind==='syntax'?await api.workspaceSyntax(draft):await api.workspaceExecute({...draft,action:kind,...(kind==='backtest'?{backtest:JSON.parse(settings)}:{})});
    setReport(response);
    if(kind==='save'&&response.ok){setRevision(response.revision);setSavedSource(source);setSavedFilename(filename);await refresh();}
    if(kind==='backtest'&&response.ok)onResult?.(response.result);
  }catch(e){setError(e.message);}finally{setBusy(false);}};
  const edit=value=>{setSource(value);setReport(null);};
  const style={fontFamily:'ui-monospace, monospace',fontSize:13,lineHeight:'20px',tabSize:4,whiteSpace:'pre',padding:12,margin:0,border:0,boxSizing:'border-box'};
  return <section className="mt-5 min-w-0 rounded-xl border border-stone-200 bg-white p-5">
    <h3 className="text-lg font-semibold">Strategy Workspace</h3>
    <p className="mt-2 rounded bg-amber-50 p-3 text-sm text-amber-900">Local trusted-code execution. Python can access your files, network and credentials. This is not a secure sandbox. Paste, load, save and syntax checks do not execute code. Only run code you trust; do not put secrets in strategy files.</p>
    <fieldset disabled={busy} className="mt-4 min-w-0">
      <div className="flex flex-wrap items-center gap-3"><button className="mini-btn" onClick={fresh}>New strategy</button><label className="text-sm">Load strategy <select className="input ml-2 max-w-full" value="" onChange={e=>load(e.target.value)}><option value="">Choose a file</option>{files.map(f=><option key={f.filename} value={f.filename}>{f.filename}{f.read_only?' (built-in, read-only)':''}</option>)}</select></label><button className="mini-btn" onClick={copy}>Make editable copy</button></div>
      <label className="mt-4 block text-sm">Filename <input className="input mt-1" value={filename} disabled={readOnly} onChange={e=>setFilename(e.target.value)}/></label>
      <p className="mt-1 text-xs text-stone-500">Saved under backend/app/backtesting/strategies/. Use _workspace_name.py with StrategySpec.key = workspace_name. Built-ins cannot be overwritten. {dirty?'Unsaved changes.':''}</p>
      <div className="relative mt-3 h-[420px] min-w-0 overflow-hidden rounded bg-slate-900">
        <pre ref={pre} aria-hidden="true" style={{...style,position:'absolute',inset:0,overflow:'hidden',pointerEvents:'none'}}>{pythonTokens(source).map((token,i)=><span key={i} style={{color:colours[token.kind]}}>{token.text}</span>)}{'\n'}</pre>
        <textarea ref={editor} aria-label="Python strategy source" readOnly={readOnly} spellCheck={false} autoCapitalize="off" autoCorrect="off" wrap="off" value={source}
          onChange={e=>edit(e.target.value)} onScroll={e=>{pre.current.scrollTop=e.target.scrollTop;pre.current.scrollLeft=e.target.scrollLeft;}}
          onKeyDown={e=>{if(e.key==='Tab'&&!readOnly){e.preventDefault();const start=e.currentTarget.selectionStart,end=e.currentTarget.selectionEnd;edit(source.slice(0,start)+'    '+source.slice(end));requestAnimationFrame(()=>editor.current.setSelectionRange(start+4,start+4));}}}
          style={{...style,position:'absolute',inset:0,width:'100%',height:'100%',background:'transparent',color:'transparent',caretColor:'white',resize:'none',overflow:'auto'}}/>
      </div>
      <div className="mt-3 flex flex-wrap gap-2"><button className="mini-btn" onClick={()=>action('syntax')}>Check syntax</button><button disabled={readOnly} className="mini-btn" onClick={()=>action('save')}>Save strategy</button></div>
      <label className="mt-4 flex items-start gap-2 text-sm"><input type="checkbox" checked={trusted} onChange={e=>setTrusted(e.target.checked)}/>I trust this Python code and allow local execution when I click an execution button.</label>
      <div className="mt-3 flex flex-wrap gap-2"><button disabled={!trusted||readOnly} className="mini-btn" onClick={()=>action('interface')}>Validate interface</button><button disabled={!trusted||readOnly} className="mini-btn" onClick={()=>action('tests')}>Run strategy tests</button></div>
      <p className="mt-2 text-xs text-stone-500">Tests are synchronous, zero-argument test_ functions in this file. They must assert behaviour using deterministic fixtures. Validation/tests time out after 15 seconds; backtests after 120 seconds. Output is captured but withheld to protect secrets.</p>
      <details className="mt-4" open><summary className="cursor-pointer text-sm font-semibold">Backtest settings</summary><p className="mt-2 text-xs text-stone-500">The common BacktestEngine and provider routing are used. Edit the JSON settings, including costs. The strategy key is taken from the workspace filename. Saved results appear under Runs; rerun workspace code from here.</p><textarea aria-label="Workspace backtest settings" className="input mt-2 h-52 font-mono text-xs" value={settings} onChange={e=>setSettings(e.target.value)}/><button disabled={!trusted||readOnly} className="mini-btn mt-2" onClick={()=>action('backtest')}>Run workspace backtest</button></details>
    </fieldset>
    {busy&&<p role="status" className="mt-3 text-sm">Working...</p>}
    {error&&<p role="alert" className="mt-3 text-red-700">{error}</p>}
    {report&&<div role="status" className="mt-4 rounded bg-stone-50 p-3 text-sm"><p>{report.ok===false?'Failed: ':''}{report.message}{report.line?` Line ${report.line}.`:''}{report.error_type?` ${report.error_type}`:''}</p>{report.tests?.map(t=><p key={t.name}>{t.passed?'PASS':'FAIL'} {t.name} {t.error_type||''}</p>)}{report.result&&<p>Completed {report.result.metrics?.trades||0} trades. {report.result.saved_run?`Saved run #${report.result.saved_run.id}. Open Runs for performance and Trade Audit.`:'Run was not saved.'}</p>}{report.output&&<p className="mt-2 text-xs text-stone-500">Captured {report.output.stdout_characters} stdout / {report.output.stderr_characters} stderr characters. {report.output.message}</p>}</div>}
  </section>;
}
