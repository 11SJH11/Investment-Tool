import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { comparison, isGoldReference } from "./runComparison.js";

const rows = [["Detected setups","detected_setups"],["Rejected / filtered setups","rejected_setups"],
  ["Unfilled / expired setups","unfilled_setups"],["Filled trades / sample N","n"],["Fill rate %","fill_rate"],
  ["Baseline setups retained %","retained_pct"],["Baseline setups removed %","removed_pct"],
  ["Unmatched baseline setups","unmatched_baseline"],["Extra variant setups","extra_setups"],
  ["Win rate %","win_rate"],["Average R","average_r"],["Total R","total_r"],["R sample N","r_n"],
  ["R profit factor","profit_factor_r"],["Max drawdown %","max_drawdown_pct"],
  ["Average MFE (R, lower bound)","average_mfe_r"],["MFE sample N","mfe_n"],
  ["Average MAE (R, lower bound)","average_mae_r"],["MAE sample N","mae_n"],
  ["Average holding minutes","average_hold_minutes"],["Consecutive losses","consecutive_losses"],["P&L (account currency)","pnl"]];
const format = (v) => v == null ? "Unavailable" : typeof v === "number" ? Number.isInteger(v) ? String(v) : v.toFixed(2) : v;

export default function RunComparison({ ids }) {
  const [runs, setRuns] = useState([]), [error, setError] = useState("");
  const [referenceId, setReferenceId] = useState(""), [dimension, setDimension] = useState("session");
  const signature = ids.join(",");
  useEffect(() => {
    let live = true; setRuns([]); setError("");
    Promise.all(ids.map(id => api.strategyLabRun(id))).then(data => {
      if (live) { setRuns(data); setReferenceId(String(data.find(isGoldReference)?.id || "")); }
    }).catch(e => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [signature]);
  if (error) return <p role="alert" className="mt-4 text-red-700">{error}</p>;
  if (!runs.length) return <p className="mt-4">Loading saved comparison…</p>;
  const reference = runs.find(r => String(r.id) === referenceId);
  const reports = runs.map(run => comparison(run, reference));
  return <div className="mt-5 min-w-0 rounded-lg border border-stone-200 bg-stone-50 p-4">
    <h4 className="text-sm font-semibold">Compare selected runs</h4>
    <p className="mt-2 text-xs">Saved snapshots only. No ranking or automatic winner. Check period, data, costs, account currency and sample size; mismatched fingerprints disable retention.</p>
    <label className="mt-3 block text-xs">Baseline reference <select className="input mt-1" value={referenceId} onChange={e => setReferenceId(e.target.value)}><option value="">None selected</option>{runs.filter(isGoldReference).map(r => <option key={r.id} value={r.id}>#{r.id} {r.name || r.result.strategy.name}</option>)}</select></label>
    {reports.map((report, i) => report.summary.warning && <p key={runs[i].id} className="mt-2 text-xs text-amber-800">#{runs[i].id}: {report.summary.warning}</p>)}
    <div className="mt-3 overflow-x-auto"><table className="min-w-[700px] text-xs"><thead><tr><th className="p-2 text-left">Metric</th>{runs.map(r => <th className="min-w-[200px] p-2 text-right" key={r.id}>#{r.id} {r.name || r.result.strategy.name}<div className="font-normal">{r.start_date} → {r.end_date} · {r.test_role}</div></th>)}</tr></thead><tbody>{rows.map(([label,key]) => <tr key={key} className="border-t border-stone-200"><td className="p-2">{label}</td>{reports.map((r,i) => <td key={runs[i].id} className="p-2 text-right">{format(r.summary[key])}</td>)}</tr>)}</tbody></table></div>
    <label className="mt-4 block text-xs">Breakdown (entry time, New York)<select className="input mt-1" value={dimension} onChange={e => setDimension(e.target.value)}>{["session","direction","weekday","month","year","regime"].map(key => <option key={key}>{key}</option>)}</select></label>
    <div className="mt-3 overflow-x-auto"><table className="min-w-[800px] text-xs"><thead><tr>{["Run","Bucket","N","Win %","Avg R","Total R","R PF","MFE R / N","MAE R / N","Hold min","P&L"].map(h => <th className="p-2 text-left" key={h}>{h}</th>)}</tr></thead><tbody>{reports.flatMap((r,i) => r.breakdowns[dimension].map(b => <tr key={`${runs[i].id}:${b.label}`} className="border-t border-stone-200">{[runs[i].id,b.label,b.n,b.win_rate,b.average_r,b.total_r,b.profit_factor_r,`${format(b.average_mfe_r)} / ${b.mfe_n}`,`${format(b.average_mae_r)} / ${b.mae_n}`,b.average_hold_minutes,b.pnl].map((v,j) => <td key={j} className="p-2">{format(v)}</td>)}</tr>))}</tbody></table></div>
  </div>;
}
