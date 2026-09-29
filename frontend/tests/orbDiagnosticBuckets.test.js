import test from 'node:test';
import assert from 'node:assert/strict';
import {orbMetrics,orbBuckets} from '../src/features/strategy-lab/orbDiagnosticBuckets.js';
import {backtestExportRows} from '../src/utils/researchExports.js';
import {toCsv} from '../src/utils/csv.js';
test('ORB buckets preserve missing versus zero, fixed boundaries and measured sample sizes',()=>{
  const trades=[{r_multiple:2,metadata:{breakout_rvol:2,mfe_r:3,mae_r:.2}},{r_multiple:-1,metadata:{breakout_rvol:2.5,mfe_r:1,mae_r:1}},{r_multiple:null,metadata:{breakout_rvol:0}},{r_multiple:1,metadata:{}}];
  const before=structuredClone(trades),rows=orbBuckets(trades,'breakout_rvol'),bucket=rows.find(r=>r.label==='2–<3');
  assert.equal(bucket.n,2);assert.equal(bucket.average_r,.5);assert.equal(bucket.total_r,1);assert.equal(bucket.profit_factor,2);assert.equal(bucket.win_rate,50);assert.equal(bucket.average_mfe,2);assert.equal(bucket.average_mae,.6);
  assert.equal(rows[0].n,1);assert.equal(rows[0].r_n,0);assert.equal(rows.at(-1).n,1);assert.deepEqual(trades,before);
});
test('all sixteen diagnostics are available to analysis and generic trade CSV',()=>{
  assert.equal(orbMetrics.length,16);
  const metadata=Object.fromEntries(orbMetrics.map(([key],i)=>[key,i===0?null:i]));
  const rows=backtestExportRows({trades:[{metadata}]});
  const csv=toCsv(rows);
  for(const [key] of orbMetrics){assert.ok(csv.includes(`"meta_${key}"`));assert.equal(orbBuckets([{metadata}],key).reduce((sum,r)=>sum+r.n,0),1);}
  assert.equal(rows[0].meta_breakout_range,null);
});
