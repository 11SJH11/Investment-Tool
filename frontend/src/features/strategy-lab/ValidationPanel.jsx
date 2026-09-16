import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";

function asDate(value) { return value ? new Date(`${value}T12:00:00Z`) : null; }
function dateString(date) { return date.toISOString().slice(0, 10); }
function addDays(date, days) { const copy = new Date(date); copy.setUTCDate(copy.getUTCDate() + days); return copy; }
function number(value, digits = 2) { return value == null || Number.isNaN(Number(value)) ? "—" : Number(value).toFixed(digits); }
function pct(value) { return value == null ? "—" : `${number(value, 2)}%`; }
function r(value) { return value == null ? "—" : `${Number(value) >= 0 ? "+" : ""}${number(value, 2)}R`; }
function money(value) { return value == null ? "—" : Intl.NumberFormat("en-GB", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value); }

function splitRange(startValue, endValue) {
  const start = asDate(startValue); const end = asDate(endValue);
  if (!start || !end || end < start) return null;
  const totalDays = Math.max(3, Math.round((end - start) / 86400000) + 1);
  const devDays = Math.max(1, Math.floor(totalDays * 0.6));
  const validationDays = Math.max(1, Math.floor(totalDays * 0.2));
  const devEnd = addDays(start, devDays - 1);
  const validationStart = addDays(devEnd, 1);
  const validationEnd = addDays(validationStart, validationDays - 1);
  const oosStart = addDays(validationEnd, 1);
  return {
    development: { start: dateString(start), end: dateString(devEnd) },
    validation: { start: dateString(validationStart), end: dateString(validationEnd) },
    out_of_sample: { start: dateString(oosStart), end: dateString(end) },
  };
}

function validateRanges(ranges) {
  const stages = [ranges.development, ranges.validation, ranges.out_of_sample];
  for (const stage of stages) {
    if (!stage?.start || !stage?.end) return "All three ranges need a start and end date.";
    if (asDate(stage.end) < asDate(stage.start)) return "Each range must end on or after it starts.";
  }
  if (asDate(ranges.validation.start) <= asDate(ranges.development.end)) return "Validation must start after development ends.";
  if (asDate(ranges.out_of_sample.start) <= asDate(ranges.validation.end)) return "Out-of-sample must start after validation ends.";
  return "";
}

const STAGES = [
  ["development", "Development"],
  ["validation", "Validation"],
  ["out_of_sample", "Out of sample"],
];

export default function ValidationPanel({ buildPayload, startDate, endDate, strategyName, strategy, refreshRuns, onError, savedExperiment = null, onClearSavedExperiment }) {
  const [ranges, setRanges] = useState(() => splitRange(startDate, endDate) || {
    development: { start: startDate, end: startDate }, validation: { start: startDate, end: startDate }, out_of_sample: { start: endDate, end: endDate },
  });
  const [name, setName] = useState("Strategy validation");
  const [notes, setNotes] = useState("");
  const [running, setRunning] = useState(false);
  const [stage, setStage] = useState("");
  const [results, setResults] = useState({});
  const numericParameters = [
    ...(strategy?.parameters || []).map((parameter) => ({ ...parameter, researchOnly: false })),
    ...(strategy?.research_parameters || []).map((parameter) => ({ ...parameter, researchOnly: true })),
  ].filter((parameter) => parameter.kind === "int" || parameter.kind === "float");
  const [sensitivityParam, setSensitivityParam] = useState("");
  const [sensitivityValues, setSensitivityValues] = useState("");
  const [sensitivityResults, setSensitivityResults] = useState([]);
  const [sensitivityRunning, setSensitivityRunning] = useState(false);

  useEffect(() => {
    if (savedExperiment) return;
    const proposed = splitRange(startDate, endDate);
    if (proposed) setRanges(proposed);
  }, [startDate, endDate, savedExperiment]);

  useEffect(() => {
    if (!savedExperiment?.runs?.length) return;
    const mapped = {}; const restored = {};
    for (const run of savedExperiment.runs) {
      if (!["development", "validation", "out_of_sample"].includes(run.test_role)) continue;
      mapped[run.test_role] = { start: run.start_date, end: run.end_date };
      restored[run.test_role] = run.result;
    }
    if (mapped.development && mapped.validation && mapped.out_of_sample) setRanges(mapped);
    setResults(restored);
    const first = savedExperiment.runs[0];
    setName((first?.name || savedExperiment.experiment_group || "Saved validation").replace(/ · (Development|Validation|Out of sample)$/i, ""));
    setNotes(first?.notes || "");
    setSensitivityResults([]);
  }, [savedExperiment]);

  useEffect(() => {
    const first = numericParameters[0];
    if (!first) { setSensitivityParam(""); setSensitivityValues(""); return; }
    setSensitivityParam(first.key);
    const base = Number(first.default); const step = Number(first.step || (first.kind === "int" ? 1 : Math.max(0.25, Math.abs(base) * 0.1)));
    const values = [-2, -1, 0, 1, 2].map((offset) => Math.max(Number(first.minimum ?? -Infinity), Math.min(Number(first.maximum ?? Infinity), base + offset * step)));
    setSensitivityValues([...new Set(values)].join(", "));
  }, [strategy?.key]);

  const rows = useMemo(() => STAGES.map(([key, label]) => ({ key, label, result: results[key] })), [results]);
  const runSuite = async () => {
    const rangeError = validateRanges(ranges);
    if (rangeError) { onError?.(rangeError); return; }
    const experiment = `${String(name || "validation").trim().replace(/\s+/g, "-").toLowerCase()}-${Date.now()}`;
    setRunning(true); setResults({}); onError?.("");
    try {
      const collected = {};
      for (const [role, label] of STAGES) {
        setStage(label);
        const range = ranges[role];
        const response = await api.runBacktest(buildPayload({
          start_date: range.start, end_date: range.end, test_role: role,
          experiment_group: experiment,
          run_name: `${name || strategyName || "Strategy"} · ${label}`,
          run_notes: notes,
          run_tags: ["validation-suite"],
          save_run: true,
        }));
        collected[role] = response;
        setResults({ ...collected });
      }
      await refreshRuns?.();
    } catch (error) {
      onError?.(error.message || String(error));
    } finally {
      setRunning(false); setStage("");
    }
  };

  const runSensitivity = async () => {
    if (!sensitivityParam) return;
    const parameter = numericParameters.find((item) => item.key === sensitivityParam);
    let values = String(sensitivityValues || "").split(",").map((value) => Number(value.trim())).filter(Number.isFinite);
    values = [...new Set(values)].slice(0, 9);
    if (!values.length) { onError?.("Enter at least one numeric sensitivity value."); return; }
    if (parameter) values = values.filter((value) => (parameter.minimum == null || value >= Number(parameter.minimum)) && (parameter.maximum == null || value <= Number(parameter.maximum)));
    if (!values.length) { onError?.("No sensitivity values are inside the parameter's allowed range."); return; }
    const experiment = `sensitivity-${sensitivityParam}-${Date.now()}`;
    setSensitivityRunning(true); setSensitivityResults([]); onError?.("");
    try {
      const output = [];
      for (const value of values) {
        const base = buildPayload();
        const response = await api.runBacktest({
          ...base, start_date: ranges.development.start, end_date: ranges.development.end,
          strategy_params: { ...(base.strategy_params || {}), [sensitivityParam]: parameter?.kind === "int" ? Math.round(value) : value },
          test_role: "development", experiment_group: experiment,
          run_name: `${strategyName || "Strategy"} · ${sensitivityParam}=${value}`,
          run_tags: ["sensitivity", sensitivityParam],
        });
        output.push({ value, result: response }); setSensitivityResults([...output]);
      }
      await refreshRuns?.();
    } catch (error) { onError?.(error.message || String(error)); }
    finally { setSensitivityRunning(false); }
  };

  return <section className="mt-5 rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
    {(strategy?.key === "momentum_vcp_breakout_baseline_v1" || savedExperiment?.runs?.some((run) => run.strategy_key === "momentum_vcp_breakout_baseline_v1")) && <p className="mb-4 rounded-lg bg-amber-50 p-3 text-xs text-amber-900">Historical universe may contain survivorship bias. Each period needs at least 250 prior daily observations within its selected dates; short validation slices may contain only warm-up.</p>}
    {savedExperiment && <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4 text-xs text-blue-900"><span><strong>Opened saved validation experiment:</strong> {savedExperiment.experiment_group}. These are stored snapshots; nothing was rerun.</span><button onClick={onClearSavedExperiment} className="rounded-md border border-blue-300 bg-white px-3 py-2">Start a new experiment</button></div>}
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div><h3 className="font-semibold">Development → validation → out-of-sample</h3><p className="mt-1 max-w-4xl text-sm text-stone-600">Run the <strong>same strategy and execution settings</strong> across three non-overlapping periods. Refine rules on development data, use validation to challenge them, and keep out-of-sample as untouched as practical.</p></div>
      <button type="button" onClick={() => { const next = splitRange(startDate, endDate); if (next) setRanges(next); }} className="rounded-md border border-stone-300 px-3 py-2 text-xs font-medium">Reset to 60 / 20 / 20</button>
    </div>

    <div className="mt-5 grid gap-4 lg:grid-cols-3">
      {STAGES.map(([role, label]) => <div key={role} className={`rounded-lg border p-4 ${role === "out_of_sample" ? "border-amber-200 bg-amber-50/40" : "border-stone-200 bg-stone-50"}`}>
        <div className="flex items-center justify-between"><h4 className="text-sm font-semibold">{label}</h4><span className="text-[10px] uppercase tracking-wide text-stone-500">{role === "development" ? "Tune here" : role === "validation" ? "Challenge" : "Final check"}</span></div>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <Field label="Start"><input type="date" className="input" value={ranges[role]?.start || ""} onChange={(e) => setRanges((old) => ({ ...old, [role]: { ...old[role], start: e.target.value } }))} /></Field>
          <Field label="End"><input type="date" className="input" value={ranges[role]?.end || ""} onChange={(e) => setRanges((old) => ({ ...old, [role]: { ...old[role], end: e.target.value } }))} /></Field>
        </div>
      </div>)}
    </div>

    <div className="mt-5 grid gap-4 lg:grid-cols-[1fr_1.5fr]">
      <Field label="Experiment name"><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. First Pullback baseline" /></Field>
      <Field label="Experiment notes"><input className="input" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="What rule set / hypothesis is being frozen for this suite?" /></Field>
    </div>
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-stone-50 p-4">
      <p className="max-w-4xl text-xs text-stone-600"><strong>Important:</strong> Ledger does not hide the out-of-sample result after you see it. Repeatedly changing rules after looking at OOS turns it into tuning data, so create a new future holdout when possible.</p>
      <button disabled={running} onClick={runSuite} className="rounded-md bg-stone-900 px-5 py-2.5 text-sm font-medium text-white disabled:opacity-50">{running ? `Running ${stage}…` : "Run 3-stage validation"}</button>
    </div>

    {Object.keys(results).length > 0 && <div className="mt-6">
      <h4 className="text-sm font-semibold">Validation comparison</h4>
      <p className="mt-1 text-xs text-stone-500">Look for performance that survives outside development rather than the prettiest development result.</p>
      <div className="mt-3 overflow-x-auto rounded-lg border border-stone-200"><table className="w-full min-w-[920px] text-sm"><thead className="bg-stone-50 text-xs uppercase tracking-wide text-stone-500"><tr><th className="px-3 py-3 text-left">Stage</th><th className="px-3 py-3 text-left">Period</th><th className="px-3 py-3 text-right">Trades</th><th className="px-3 py-3 text-right">Win rate</th><th className="px-3 py-3 text-right">Expectancy</th><th className="px-3 py-3 text-right">Profit factor</th><th className="px-3 py-3 text-right">Total R</th><th className="px-3 py-3 text-right">Return</th><th className="px-3 py-3 text-right">Max DD</th><th className="px-3 py-3 text-right">Net P&L</th></tr></thead><tbody className="divide-y divide-stone-100">{rows.map(({ key, label, result }) => { const m = result?.metrics || {}; return <tr key={key}><td className="px-3 py-3 font-semibold">{label}</td><td className="whitespace-nowrap px-3 py-3 text-xs">{ranges[key]?.start} → {ranges[key]?.end}</td><td className="px-3 py-3 text-right">{result ? m.trades : "—"}</td><td className="px-3 py-3 text-right">{result ? pct(m.win_rate_pct) : "—"}</td><td className="px-3 py-3 text-right">{result ? r(m.expectancy_r) : "—"}</td><td className="px-3 py-3 text-right">{result ? number(m.profit_factor_r) : "—"}</td><td className="px-3 py-3 text-right">{result ? r(m.total_r) : "—"}</td><td className="px-3 py-3 text-right">{result ? pct(m.return_pct) : "—"}</td><td className="px-3 py-3 text-right">{result ? pct(m.max_drawdown_pct) : "—"}</td><td className="px-3 py-3 text-right">{result ? money(m.net_pnl) : "—"}</td></tr>; })}</tbody></table></div>
      <StabilitySummary results={results} />
    </div>}

    <div className="mt-7 border-t border-stone-100 pt-5">
      <div><h4 className="text-sm font-semibold">One-parameter sensitivity</h4><p className="mt-1 max-w-4xl text-xs text-stone-500">Test nearby values on the <strong>development period only</strong>. This is a robustness check, not a winner picker: if small parameter changes destroy the result, the apparent edge may be fragile. Strategy-owned stop/target values can appear here as temporary research overrides without becoming ordinary run settings.</p></div>
      {numericParameters.length ? <><div className="mt-4 grid gap-4 lg:grid-cols-[1fr_2fr_auto]"><Field label="Parameter"><select className="input" value={sensitivityParam} onChange={(e) => { const key = e.target.value; setSensitivityParam(key); const p = numericParameters.find((item) => item.key === key); const base = Number(p?.default || 0); const step = Number(p?.step || (p?.kind === "int" ? 1 : 0.25)); setSensitivityValues([-2,-1,0,1,2].map((offset) => base + offset * step).join(", ")); }}>{numericParameters.map((parameter) => <option key={parameter.key} value={parameter.key}>{parameter.label}{parameter.researchOnly ? " · strategy-owned research" : ""}</option>)}</select></Field><Field label="Values · comma separated · max 9"><input className="input" value={sensitivityValues} onChange={(e) => setSensitivityValues(e.target.value)} /></Field><div className="flex items-end"><button disabled={sensitivityRunning} onClick={runSensitivity} className="rounded-md border border-stone-900 bg-stone-900 px-4 py-2 text-xs font-medium text-white disabled:opacity-50">{sensitivityRunning ? "Running sweep…" : "Run sensitivity"}</button></div></div>
      {numericParameters.find((item) => item.key === sensitivityParam)?.researchOnly && <p className="mt-2 text-xs text-blue-700">This value belongs to the strategy code in normal runs. Sensitivity temporarily overrides it for research only; the source default is not changed.</p>}
      {sensitivityResults.length > 0 && <div className="mt-4 overflow-x-auto rounded-lg border border-stone-200"><table className="w-full min-w-[760px] text-sm"><thead className="bg-stone-50 text-xs uppercase tracking-wide text-stone-500"><tr><th className="px-3 py-3 text-left">{sensitivityParam}</th><th className="px-3 py-3 text-right">Trades</th><th className="px-3 py-3 text-right">Expectancy</th><th className="px-3 py-3 text-right">PF</th><th className="px-3 py-3 text-right">Total R</th><th className="px-3 py-3 text-right">Return</th><th className="px-3 py-3 text-right">Max DD</th></tr></thead><tbody className="divide-y divide-stone-100">{sensitivityResults.map(({ value, result }) => { const m = result.metrics || {}; return <tr key={value}><td className="px-3 py-3 font-semibold">{value}</td><td className="px-3 py-3 text-right">{m.trades}</td><td className="px-3 py-3 text-right">{r(m.expectancy_r)}</td><td className="px-3 py-3 text-right">{number(m.profit_factor_r)}</td><td className="px-3 py-3 text-right">{r(m.total_r)}</td><td className="px-3 py-3 text-right">{pct(m.return_pct)}</td><td className="px-3 py-3 text-right">{pct(m.max_drawdown_pct)}</td></tr>; })}</tbody></table></div>}
      {sensitivityResults.length > 1 && <SensitivitySummary rows={sensitivityResults} />}</> : <p className="mt-3 text-xs text-stone-500">This strategy has no numeric parameters to sweep.</p>}
    </div>
  </section>;
}

function SensitivitySummary({ rows }) {
  const valid = rows.map(({ value, result }) => ({ value, trades: Number(result?.metrics?.trades || 0), expectancy: Number(result?.metrics?.expectancy_r) })).filter((item) => Number.isFinite(item.expectancy));
  if (valid.length < 2) return null;
  const positive = valid.filter((item) => item.expectancy > 0).length;
  const min = Math.min(...valid.map((item) => item.expectancy)); const max = Math.max(...valid.map((item) => item.expectancy));
  const small = valid.filter((item) => item.trades < 30).length;
  let text = `${positive}/${valid.length} tested values had positive expectancy; the spread from worst to best was ${(max - min).toFixed(2)}R per trade.`;
  if (positive === valid.length) text += " The whole tested neighbourhood stayed positive, which is more reassuring than a single isolated peak.";
  else if (positive <= 1) text += " Positive performance is concentrated in very few values, so this parameter region looks fragile until validated on much more data.";
  else text += " Results are mixed across nearby values, so avoid treating the best row as an automatically optimal setting.";
  if (small) text += ` ${small}/${valid.length} rows have fewer than 30 trades, so sample noise is still substantial.`;
  return <div className="mt-3 rounded-lg border border-stone-200 bg-stone-50 p-4"><p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Sensitivity read</p><p className="mt-2 text-sm text-stone-700">{text}</p></div>;
}

function StabilitySummary({ results }) {
  const dev = results.development?.metrics; const val = results.validation?.metrics; const oos = results.out_of_sample?.metrics;
  if (!dev || !val || !oos) return null;
  const expectancies = [dev.expectancy_r, val.expectancy_r, oos.expectancy_r].map(Number);
  const positive = expectancies.filter((value) => Number.isFinite(value) && value > 0).length;
  const development = Number(dev.expectancy_r); const validation = Number(val.expectancy_r); const out = Number(oos.expectancy_r);
  let message = `${positive}/3 stages had positive realised-R expectancy.`;
  if (development > 0 && (validation <= 0 || out <= 0)) message += " Performance weakened outside development, which is a warning against treating the development edge as established.";
  else if (development > 0 && validation > 0 && out > 0) message += " The sign of expectancy survived both holdouts; this is encouraging evidence, not proof of a future edge.";
  else if (development <= 0) message += " The baseline was not positive even in development, so parameter tuning should be justified by a clear strategy hypothesis rather than searching blindly.";
  return <div className="mt-4 rounded-lg border border-stone-200 bg-stone-50 p-4"><p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Stability check</p><p className="mt-2 text-sm text-stone-700">{message}</p></div>;
}

function Field({ label, children }) { return <label className="block"><span className="mb-1 block text-xs font-medium text-stone-500">{label}</span>{children}</label>; }
