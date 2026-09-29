import {tradeDiagnostics, sampleStats} from './tradeDiagnostics.js';

export const experimentMetrics = [
  ['expectancy_r','Average R'], ['total_r','Total R'], ['profit_factor_r','Profit factor'],
  ['max_drawdown_r','Max drawdown R'], ['max_drawdown_pct','Max drawdown %'],
  ['return_pct','Return %'], ['win_rate_pct','Win rate %'], ['trades','Trade count'],
  ['average_mfe','Average MFE R'], ['average_mae','Average MAE R'],
  ['stop_pct','Stop %'], ['target_pct','Target %'],
];
export function runMetrics(run) {
  if (!run) return null;
  const result=run.result || {}, trades=result.trades || [];
  const stats=sampleStats(trades.map(t=>({...t,...tradeDiagnostics(t)})));
  return {...result.metrics, average_mfe:stats.average_mfe, average_mae:stats.average_mae,
    mfe_n:stats.mfe_n,mae_n:stats.mae_n,
    stop_pct:stats.n?100*stats.stop/stats.n:null,target_pct:stats.n?100*stats.target/stats.n:null};
}
export function axisDisplay(axis,value) {
  const i=(axis?.values||[]).findIndex(v=>v===value);
  return i>=0?(axis.labels?.[i]??String(value)):String(value);
}
export function cellDisplay(plan,values) {
  return (values||[]).map((v,i)=>axisDisplay(plan?.axes?.[i],v)).join(' × ');
}
export function experimentCells(plan, runs=[], jobs=[], persistedCells=[]) {
  return (plan?.cells||[]).map((values,index)=>{
    const run=runs.find(r=>r.config?.research_experiment?.cell_index===index);
    const job=jobs.find(j=>j.payload?.research_experiment?.cell_index===index);
    const persisted=persistedCells.find(c=>c.index===index),metrics=runMetrics(run);
    const control=(plan?.axes||[]).every((axis,i)=>axis.mode!=='bands'&&values[i]===axis.default);
    return {index,values,runId:run?.id??persisted?.run_id,status:run?'completed':persisted?.status||job?.status||'queued',
      progress:job?.progress,error:persisted?.error||job?.error,metrics,lowN:metrics!=null&&metrics.trades<30,
      control};
  });
}
export function cellTooltip(cell, plan) {
  const m=cell.metrics||{}, fmt=v=>v==null?'—':Number(v).toFixed(2);
  return [plan.axes.map((a,i)=>`${a.label}: ${axisDisplay(a,cell.values[i])}${a.mode==='bands'?' [lower, upper)':''}`).join(' · '),cell.status,
    `N ${m.trades??'—'} · Avg R ${fmt(m.expectancy_r)} · PF ${fmt(m.profit_factor_r)}`,
    `Total R ${fmt(m.total_r)} · Max DD ${fmt(m.max_drawdown_r)}R / ${fmt(m.max_drawdown_pct)}% · Win ${fmt(m.win_rate_pct)}%`,
    `MFE N ${m.mfe_n??'—'} · MAE N ${m.mae_n??'—'}`,
    cell.lowN?'Low sample (N < 30)':'',cell.control?'Declared default control':'',cell.error||''].filter(Boolean).join('\n');
}
export function heatScale(cells, metric, valueAccessor=null) {
  const floor={expectancy_r:1,total_r:10,profit_factor_r:2,max_drawdown_r:5,
    max_drawdown_pct:10,return_pct:10,win_rate_pct:100,trades:30,average_mfe:1,average_mae:1}[metric]||1;
  const values=cells.map(c=>valueAccessor?valueAccessor(c):c.metrics?.[metric]).filter(Number.isFinite);
  return Math.max(floor,...values.map(v=>Math.abs(v)));
}

const mean=values=>{const finite=values.filter(Number.isFinite);return finite.length?finite.reduce((a,b)=>a+b,0)/finite.length:null;};
export function interactionAnalysis(plan,cells,metric) {
  if(plan?.kind!=='interaction') return null;
  const xAxis=plan.axes[0], yAxis=plan.axes[1];
  const complete=cells.filter(c=>Number.isFinite(c.metrics?.[metric]));
  const grand=mean(complete.map(c=>Number(c.metrics[metric])));
  const marginal=(axis,index)=>axis.values.map(value=>{
    const group=complete.filter(c=>c.values[index]===value),m=mean(group.map(c=>Number(c.metrics[metric])));
    return {value,label:axisDisplay(axis,value),mean:m,effect:Number.isFinite(m)&&Number.isFinite(grand)?m-grand:null,
      cells:group.length,trades:group.reduce((n,c)=>n+Number(c.metrics?.trades||0),0)};
  });
  const xMarginals=marginal(xAxis,0), yMarginals=marginal(yAxis,1);
  const xMeans=new Map(xMarginals.map(r=>[r.value,r.mean])),yMeans=new Map(yMarginals.map(r=>[r.value,r.mean]));
  const residuals=new Map();
  for(const c of complete){const xm=xMeans.get(c.values[0]),ym=yMeans.get(c.values[1]);if([grand,xm,ym].every(Number.isFinite))residuals.set(c.index,Number(c.metrics[metric])-xm-ym+grand);}
  const disjoint=xAxis.mode==='bands'&&yAxis.mode==='bands';
  const interpretation=disjoint
    ? 'Both axes are non-overlapping bands, so neighbouring rows/columns describe distinct parameter intervals.'
    : 'At least one axis is a cumulative threshold. Those cells can contain overlapping trades, so read the marginals as threshold response rather than disjoint market buckets; use band mode for direct interval relationships.';
  return {grand,xMarginals,yMarginals,residuals,disjoint,
    note:`Interaction residual = observed cell metric − X marginal mean − Y marginal mean + overall mean. ${interpretation} Descriptive development-data evidence only; it is not a causal effect or an optimizer.`};
}
