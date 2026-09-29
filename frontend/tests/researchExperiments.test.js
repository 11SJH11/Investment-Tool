import test from 'node:test';
import assert from 'node:assert/strict';
import {experimentCells,cellTooltip,heatScale,runMetrics} from '../src/features/strategy-lab/researchExperiments.js';
const plan={axes:[{label:'ATR',default:-1},{label:'RVOL',default:-1}],cells:[[-1,-1],[-1,1],[1,-1],[1,1]]};
const run=(i,id,n=10)=>({id,config:{research_experiment:{cell_index:i}},result:{metrics:{trades:n,expectancy_r:-.02,total_r:-.2,profit_factor_r:.9,max_drawdown_r:2,win_rate_pct:40},trades:[]}});
test('exact cells retain defaults, failures, pending results and saved-run IDs',()=>{
 const cells=experimentCells(plan,[run(0,91),run(3,95,40)],[{status:'failed',error:'Unavailable',payload:{research_experiment:{cell_index:1}}},{status:'running',payload:{research_experiment:{cell_index:2}}}]);
 assert.equal(cells.length,4);assert.equal(cells[0].control,true);assert.equal(cells[0].lowN,true);
 assert.equal(cells[3].runId,95);assert.equal(cells[3].lowN,false);
 assert.equal(cells[1].status,'failed');assert.equal(cells[2].status,'running');
 assert.match(cellTooltip(cells[0],plan),/N 10.*Avg R -0.02/);assert.match(cellTooltip(cells[1],plan),/Unavailable/);
 assert.equal(cells[0].metrics.expectancy_r,-.02);
 assert.deepEqual(cells.map(c=>c.values),plan.cells);
});
test('empty and incomplete grids preserve every cell without inventing metrics',()=>{
 const cells=experimentCells(plan);
 assert.equal(cells.length,4);assert(cells.every(c=>c.metrics===null&&c.runId===undefined));
 assert.equal(runMetrics(null),null);
});
test('parent cell references preserve partial failure and exact drill-down',()=>{
 const cells=experimentCells(plan,[run(0,91)],[],[{index:0,status:'completed',run_id:91},{index:1,status:'failed',error:'Cell failure'},{index:2,status:'cancelled'},{index:3,status:'completed',run_id:99}]);
 assert.equal(cells[1].status,'failed');assert.equal(cells[2].status,'cancelled');
 assert.equal(cells[3].runId,99);assert.equal(cells[3].metrics,null);
 assert.match(cellTooltip(cells[1],plan),/Cell failure/);
});
test('heat scale does not exaggerate tiny expectancy differences',()=>{
 assert.equal(heatScale([{metrics:{expectancy_r:.001}},{metrics:{expectancy_r:-.002}}],'expectancy_r'),1);
});
test('recorded excursion samples and stop/target percentages remain descriptive',()=>{
 const metrics=runMetrics({result:{metrics:{trades:3},trades:[{exit_reason:'stop_loss',metadata:{mfe_r:1,mae_r:.5}},{exit_reason:'take_profit',metadata:{mfe_r:2}},{exit_reason:'session_close'}]}});
 assert.equal(metrics.average_mfe,1.5);assert.equal(metrics.mfe_n,2);assert.equal(metrics.mae_n,1);
 assert.equal(metrics.stop_pct,100/3);assert.equal(metrics.target_pct,100/3);
});

import {axisDisplay,cellDisplay,interactionAnalysis} from '../src/features/strategy-lab/researchExperiments.js';

test('band axes use explicit non-overlapping labels and are never mistaken for the default control',()=>{
 const bandPlan={kind:'interaction',axes:[
   {label:'ATR band',mode:'bands',values:[1,1.25],labels:['1.00–1.25','1.25–1.50'],default:-1},
   {label:'RVOL',mode:'explicit',values:[-1,1],labels:['off','1.00'],default:-1},
 ],cells:[[1,-1],[1.25,-1]]};
 const cells=experimentCells(bandPlan,[run(0,101,40),run(1,102,40)]);
 assert.equal(axisDisplay(bandPlan.axes[0],1),'1.00–1.25');
 assert.equal(cellDisplay(bandPlan,[1,-1]),'1.00–1.25 × off');
 assert.equal(cells[0].control,false);
});

test('interaction analysis reports marginals, deltas and additive residuals',()=>{
 const interaction={kind:'interaction',axes:[
   {label:'X',mode:'bands',values:[1,2],labels:['1–2','2–3']},
   {label:'Y',mode:'bands',values:[10,20],labels:['10–20','20–30']},
 ],cells:[[1,10],[1,20],[2,10],[2,20]]};
 const cells=interaction.cells.map((values,index)=>({index,values,metrics:{expectancy_r:[1,3,5,11][index],trades:40}}));
 const analysis=interactionAnalysis(interaction,cells,'expectancy_r');
 assert.equal(analysis.grand,5);
 assert.deepEqual(analysis.xMarginals.map(r=>r.mean),[2,8]);
 assert.deepEqual(analysis.xMarginals.map(r=>r.effect),[-3,3]);
 assert.deepEqual(analysis.yMarginals.map(r=>r.mean),[3,7]);
 assert.deepEqual(analysis.yMarginals.map(r=>r.effect),[-2,2]);
 assert.equal(analysis.residuals.get(0),1);
 assert.equal(analysis.residuals.get(1),-1);
 assert.equal(analysis.residuals.get(2),-1);
 assert.equal(analysis.residuals.get(3),1);
 assert.equal(analysis.disjoint,true);
 assert.match(analysis.note,/non-overlapping bands/);
});

test('interaction analysis warns that minimum-threshold grids overlap',()=>{
 const thresholdPlan={kind:'interaction',axes:[
   {label:'Min ATR',mode:'explicit',values:[1,1.5]},
   {label:'Min RVOL',mode:'explicit',values:[.5,1]},
 ],cells:[[1,.5],[1,1],[1.5,.5],[1.5,1]]};
 const cells=thresholdPlan.cells.map((values,index)=>({index,values,metrics:{expectancy_r:index,trades:40}}));
 const analysis=interactionAnalysis(thresholdPlan,cells,'expectancy_r');
 assert.equal(analysis.disjoint,false);
 assert.match(analysis.note,/overlapping trades/);
 assert.match(analysis.note,/band mode/);
});
