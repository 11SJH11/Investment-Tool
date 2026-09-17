import test from "node:test";
import assert from "node:assert/strict";
import { comparison, retention, tradeStatistics } from "../src/features/strategy-lab/runComparison.js";

const setup = (id, passed=true) => ({ symbol:"XAUUSD", direction:"long", status:passed?"filled":"rejected",
  metadata:{ sweep_time:`sweep-${id}`, type3_confirmation_time:`confirm-${id}`, filters_passed:passed } });
const run = (key,setups=[],trades=[]) => ({result:{strategy:{key},setups,trades,
  data:{comparison_signature:"identical"},metrics:{net_pnl:20,max_drawdown_pct:-1,longest_losing_streak:2}}});
const reference = (...setups) => run("xau_type3_experiment_reference_v1",setups);

test("retention matches identities and separates path-dependent omissions and extras",()=>{
  const ref=reference(setup(1),setup(2),setup(3),setup(4));
  const variant=run("xau_type3_experiment_fvg_v1",[setup(1),setup(2,false),setup(3),setup(5)]);
  const value=retention(variant,ref);
  assert.equal(value.retained_pct,50);assert.equal(value.removed_pct,25);
  assert.equal(value.unmatched_baseline,1);assert.equal(value.extra_setups,1);
  assert.match(value.warning,/occupancy/);
});

test("different costs/data and legacy missing signatures disable retention",()=>{
  const ref=reference(setup(1)), variant=reference(setup(1));
  variant.result.data.comparison_signature="different";
  assert.equal(retention(variant,ref).retained_pct,null);
  delete variant.result.data.comparison_signature;
  assert.equal(retention(variant,ref).removed_pct,null);
  assert.equal(retention(variant,null).retained_pct,null);
  assert.equal(retention(reference(),reference()).retained_pct,null);
});

test("missing excursion measurements stay unavailable with their sample count",()=>{
  const stats=tradeStatistics([{r_multiple:2,result:"win",net_pnl:20,entry_time:"2026-01-01T15:00Z",exit_time:"2026-01-01T15:10Z"}]);
  assert.equal(stats.average_mfe_r,null);assert.equal(stats.mfe_n,0);
  assert.equal(stats.profit_factor_r,"No losses");assert.equal(stats.average_hold_minutes,10);
});

test("DXY-dependent runs explicitly suppress unsupported performance conclusions",()=>{
  for(const key of ["dxy","dxy_session","full_candidate"]){
    const report=comparison(run(`xau_type3_experiment_${key}_v1`,[setup(1,false)]),reference(setup(1)));
    assert.equal(report.summary.detected_setups,1);assert.equal(report.summary.rejected_setups,1);
    assert.equal(report.summary.pnl,null);assert.match(report.summary.warning,/DXY data unavailable/);
  }
});

test("breakdowns use New York entry date and retain R and excursion sample sizes",()=>{
  const trade={direction:"long",entry_time:"2026-01-01T02:00Z",exit_time:"2026-01-01T02:30Z",r_multiple:-1,
    result:"loss",net_pnl:-10,metadata:{session:"Asia",mfe_r:.5,mae_r:1}};
  const report=comparison(run("xau_type3_experiment_reference_v1",[],[trade]),null);
  assert.equal(report.breakdowns.year[0].label,"2025");
  assert.equal(report.breakdowns.weekday[0].label,"Wednesday");
  assert.equal(report.breakdowns.regime[0].label,"Unavailable");
  assert.equal(report.breakdowns.session[0].average_mfe_r,.5);
  assert.equal(report.summary.r_n,1);
});
