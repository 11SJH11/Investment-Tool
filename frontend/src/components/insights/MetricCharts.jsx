import {useMemo,useState} from 'react';

function orderedRows(rows,valueKey,order) {
  const copy=[...(rows||[])];
  const numeric=(key,direction=-1)=>copy.sort((a,b)=>direction*((Number(a[key])||0)-(Number(b[key])||0))||String(a.label||'').localeCompare(String(b.label||'')));
  if(order==='best')return numeric(valueKey,-1);
  if(order==='worst')return numeric(valueKey,1);
  if(order==='sample')return numeric('trades',-1);
  return copy;
}
export function MetricBars({title,rows,valueKey='average_r',labelKey='label',format=v=>Number(v).toFixed(2),note,sortable=true}) {
  const [order,setOrder]=useState('original');
  const shown=useMemo(()=>orderedRows(rows,valueKey,order),[rows,valueKey,order]);
  const values=shown.filter(r=>typeof r[valueKey]==='number'&&Number.isFinite(r[valueKey]));const max=Math.max(1,...values.map(r=>Math.abs(r[valueKey])));
  return <figure className="insight-panel"><div className="metric-chart-head"><h4>{title}</h4>{sortable&&rows.length>1&&<select aria-label={`Sort ${title}`} className="input table-density" value={order} onChange={e=>setOrder(e.target.value)}><option value="original">Original order</option><option value="best">Best → worst</option><option value="worst">Worst → best</option><option value="sample">Largest sample</option></select>}</div><div className="metric-bars">{shown.map((r,i)=><div key={`${r[labelKey]}-${i}`} className="metric-bar-row"><span title={r[labelKey]}>{r[labelKey]}</span><div className="metric-bar-track"><span className={valueKey.includes('drawdown')?'negative-bar':valueKey==='n'?'info-bar':r[valueKey]<0?'negative-bar':'positive-bar'} style={{width:`${typeof r[valueKey]==='number'?Math.abs(r[valueKey])/max*100:0}%`}}/></div><span>{typeof r[valueKey]==='number'?format(r[valueKey]):'Unavailable'} <small>N={r.trades??r.n??0}{(r.trades??r.n??0)<20?' · Low sample':''}</small></span></div>)}</div>{!shown.length&&<p className="empty-state">No measured results yet.</p>}<figcaption>{note||'Descriptive results. N < 20 is labelled low sample; larger samples do not prove an edge.'}</figcaption></figure>;
}
export function SeriesChart({title,points,valueKey,description}) {
  const valid=points.filter(p=>typeof p[valueKey]==='number'&&Number.isFinite(p[valueKey]));const min=Math.min(0,...valid.map(p=>p[valueKey])),max=Math.max(0,...valid.map(p=>p[valueKey]));const x=i=>35+i*610/Math.max(1,valid.length-1),y=v=>142-(v-min)/Math.max(.001,max-min)*112;
  const showPoints=valid.length<=120;
  return <figure className="insight-panel"><h4>{title}</h4><svg viewBox="0 0 680 170" role="img" aria-label={`${title}, ${valid.length} observations`}><line x1="35" x2="650" y1={y(0)} y2={y(0)} stroke="var(--ledger-border-strong)"/><text x="5" y="28" fill="var(--ledger-muted)" fontSize="11">{max.toFixed(1)}</text><text x="5" y="145" fill="var(--ledger-muted)" fontSize="11">{min.toFixed(1)}</text><polyline points={valid.map((p,i)=>`${x(i)},${y(p[valueKey])}`).join(' ')} fill="none" stroke="var(--color-info)" strokeWidth="2"/>{showPoints&&valid.map((p,i)=><circle key={p.id??i} cx={x(i)} cy={y(p[valueKey])} r="2.5" fill="var(--color-info)"><title>{p.timestamp}: {p[valueKey].toFixed(3)}R{p.n?` · N=${p.n}${p.n<20?' · Low sample':''}`:''}</title></circle>)}<text x="35" y="165" fill="var(--ledger-muted)" fontSize="10">{valid[0]?.timestamp?.slice(0,10)||'No results'}</text><text x="570" y="165" fill="var(--ledger-muted)" fontSize="10">{valid.at(-1)?.timestamp?.slice(0,10)}</text></svg><figcaption>{description} N = {valid.length}.{showPoints?' Hover points for dates.':' Dense samples render as a line for readability.'}</figcaption></figure>;
}
