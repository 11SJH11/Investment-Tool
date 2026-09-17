import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import SymbolSearch from "../../components/SymbolSearch";
import { TIMEZONE_OPTIONS } from "../../utils/timezones";
import PerformanceChart from "./PerformanceChart";
import TradeAuditChart from "./TradeAuditChart";
import ValidationPanel from "./ValidationPanel";
import ReplayPanel from "./ReplayPanel";
import StrategyWorkspace from "./StrategyWorkspace";
import RunComparison from "./RunComparison.jsx";

const timeframes = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"];
const weekdays = [[0, "Mon"], [1, "Tue"], [2, "Wed"], [3, "Thu"], [4, "Fri"]];
const roles = [
  ["development", "Development"], ["validation", "Validation"],
  ["out_of_sample", "Out of sample"], ["unclassified", "Unclassified"],
];

function isoDateOffset(days) { const date = new Date(); date.setDate(date.getDate() + days); return date.toISOString().slice(0, 10); }
function number(value, digits = 2) { return value == null || Number.isNaN(Number(value)) ? "—" : Number(value).toFixed(digits); }
function pct(value) { return value == null ? "—" : `${number(value, 2)}%`; }
function money(value) { return value == null ? "—" : Intl.NumberFormat("en-GB", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value); }
function r(value) { return value == null ? "—" : `${Number(value) >= 0 ? "+" : ""}${number(value, 2)}R`; }
function formatDate(value) { if (!value) return "—"; return new Intl.DateTimeFormat("en-GB", { dateStyle: "short", timeStyle: "short", timeZone: "America/New_York" }).format(new Date(value)); }

export default function StrategyLabPage({ initialTab = "Backtest", standaloneTab = null, onWorkspaceDirty }) {
  const [tab, setTab] = useState(initialTab);
  const [strategies, setStrategies] = useState([]);
  const [indicators, setIndicators] = useState([]);
  const [runs, setRuns] = useState([]);
  const [strategyKey, setStrategyKey] = useState("");
  const [params, setParams] = useState({});
  const [symbols, setSymbols] = useState(["AAPL"]);
  const [symbolInput, setSymbolInput] = useState("");
  const [entryWindows, setEntryWindows] = useState([]);
  const [selectedWeekdays, setSelectedWeekdays] = useState([0, 1, 2, 3, 4]);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [runMeta, setRunMeta] = useState({ name: "", notes: "", tags: "", test_role: "development" });
  const [form, setForm] = useState({
    start_date: isoDateOffset(-90), end_date: isoDateOffset(-1), primary_timeframe: "5m", session: "auto",
    starting_balance: "10000", sizing_mode: "risk_pct", risk_value: "1", commission_per_order: "0",
    slippage_bps: "0", spread_bps: "0", max_leverage: "1", max_open_positions: "5", same_bar_policy: "stop_first",
    allow_overnight: "true", force_close_time: "", max_trades_per_day: "", max_daily_loss_r: "",
    max_consecutive_losses: "", cooldown_minutes: "0",
  });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [savedExperiment, setSavedExperiment] = useState(null);
  useEffect(() => { if (initialTab) setTab(initialTab); }, [initialTab]);

  const refreshRuns = useCallback(() => api.strategyLabRuns(100).then((data) => setRuns(data.runs || [])).catch(() => {}), []);
  useEffect(() => {
    Promise.all([api.strategyLabStrategies(), api.strategyLabIndicators()])
      .then(([s, i]) => {
        const list = s.strategies || [];
        setStrategies(list); setIndicators(i.indicators || []);
        if (list.length) setStrategyKey(list[0].key);
      })
      .catch((e) => setError(e.message));
    refreshRuns();
  }, [refreshRuns]);

  const strategy = strategies.find((item) => item.key === strategyKey);
  useEffect(() => {
    if (!strategy) return;
    setParams({ ...(strategy.defaults || {}) });
    if ((strategy.key === "xau_liquidity_type3_baseline_v1" || strategy.key.startsWith("xau_type3_experiment_"))) {
      setSymbols(["XAUUSD"]);
      setEntryWindows([]);
      setForm((old) => ({ ...old, primary_timeframe: "1m", session: "auto", allow_overnight: "true", force_close_time: "" }));
    } else if (strategy.key === "momentum_vcp_breakout_baseline_v1") {
      setEntryWindows([]);
      setForm((old) => ({ ...old, primary_timeframe: "1d", session: "auto", allow_overnight: "true", force_close_time: "" }));
    } else if (strategy.timeframes?.[0]) {
      setForm((old) => ({ ...old, primary_timeframe: strategy.timeframes[0] }));
    }
    setResult(null);
  }, [strategyKey, strategies.length]);

  const addSymbol = (ticker) => {
    const value = String(ticker || symbolInput).trim().toUpperCase();
    if (!value) return;
    setSymbols((old) => old.includes(value) ? old : [...old, value]);
    setSymbolInput("");
  };
  const updateSession = (session) => {
    setForm((old) => ({ ...old, session }));
    // Session selection controls which bars are loaded. Entry windows are an
    // independent strategy/account filter and are intentionally not rewritten.
  };

  const buildPayload = (overrides = {}) => ({
    strategy_key: strategyKey, symbols, start_date: form.start_date, end_date: form.end_date,
    primary_timeframe: form.primary_timeframe, additional_timeframes: [], session: form.session,
    strategy_params: normaliseParams(strategy, params), starting_balance: Number(form.starting_balance),
    sizing_mode: form.sizing_mode, risk_value: Number(form.risk_value), commission_per_order: Number(form.commission_per_order),
    slippage_bps: Number(form.slippage_bps), spread_bps: Number(form.spread_bps), max_leverage: Number(form.max_leverage),
    max_open_positions: Number(form.max_open_positions), same_bar_policy: form.same_bar_policy,
    entry_windows: entryWindows.filter((w) => w.start && w.end), trading_weekdays: selectedWeekdays,
    allow_overnight: form.allow_overnight === "true", force_close_time: form.allow_overnight === "true" ? null : form.force_close_time,
    max_trades_per_day: optionalNumber(form.max_trades_per_day), max_daily_loss_r: optionalNumber(form.max_daily_loss_r),
    max_consecutive_losses: optionalNumber(form.max_consecutive_losses), cooldown_minutes: Number(form.cooldown_minutes || 0),
    save_run: true, run_name: runMeta.name, run_notes: runMeta.notes, test_role: runMeta.test_role,
    run_tags: String(runMeta.tags || "").split(",").map((item) => item.trim()).filter(Boolean),
    ...overrides,
  });

  const run = async () => {
    if (!strategyKey || !symbols.length) return;
    setLoading(true); setError(""); setResult(null);
    try {
      const response = await api.runBacktest(buildPayload());
      setResult(response);
      refreshRuns();
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  const openSavedRun = async (runId) => {
    setError("");
    try {
      const saved = await api.strategyLabRun(runId);
      setResult({ ...saved.result, saved_run: { id: saved.id, name: saved.name, test_role: saved.test_role, created_at: saved.created_at } });
      setTab("Backtest");
    } catch (e) { setError(e.message); }
  };
  const openSavedExperiment = async (group) => {
    setError("");
    try {
      const suite = await api.strategyLabExperiment(group);
      setSavedExperiment(suite);
      setTab("Validation");
    } catch (e) { setError(e.message); }
  };

  const useSavedSettings = async (runId) => {
    setError("");
    try {
      const saved = await api.strategyLabRun(runId);
      const config = saved.config || {};
      if (config.workspace) {
        setTab("Strategy Workspace");
        setError(`This is a workspace run. Load ${config.workspace.filename} and rerun it from Strategy Workspace. Saved source SHA-256: ${config.workspace.source_sha256}.`);
        return;
      }
      setStrategyKey(config.strategy_key || saved.strategy_key);
      setSymbols(config.symbols || saved.symbols || []);
      setForm((old) => ({
        ...old,
        start_date: config.start_date || old.start_date, end_date: config.end_date || old.end_date,
        primary_timeframe: config.primary_timeframe || old.primary_timeframe, session: config.session || old.session,
        starting_balance: String(config.starting_balance ?? old.starting_balance), sizing_mode: config.sizing_mode || old.sizing_mode,
        risk_value: String(config.risk_value ?? old.risk_value), commission_per_order: String(config.commission_per_order ?? 0),
        slippage_bps: String(config.slippage_bps ?? 0), spread_bps: String(config.spread_bps ?? 0),
        max_leverage: String(config.max_leverage ?? 1), max_open_positions: String(config.max_open_positions ?? 5),
        same_bar_policy: config.same_bar_policy || "stop_first", allow_overnight: String(Boolean(config.allow_overnight)),
        force_close_time: config.force_close_time || "",
        max_trades_per_day: config.max_trades_per_day ?? "", max_daily_loss_r: config.max_daily_loss_r ?? "",
        max_consecutive_losses: config.max_consecutive_losses ?? "", cooldown_minutes: String(config.cooldown_minutes ?? 0),
      }));
      setEntryWindows(config.entry_windows?.length ? config.entry_windows : []);
      setSelectedWeekdays(config.trading_weekdays || [0, 1, 2, 3, 4]);
      setRunMeta({ name: saved.name ? `${saved.name} · copy` : "", notes: saved.notes || "", tags: (saved.tags || []).join(", "), test_role: saved.test_role || "development" });
      setTimeout(() => setParams({ ...(config.strategy_params || {}) }), 0);
      setResult(null); setTab("Backtest");
    } catch (e) { setError(e.message); }
  };

  return <div className={standaloneTab === "Replay" ? "w-full max-w-none" : "max-w-[1600px]"}>
    <div><p className="text-xs uppercase tracking-widest text-stone-500">Ledger</p><h2 className="mt-1 text-3xl font-semibold">{standaloneTab === "Replay" ? "Replay" : standaloneTab === "Backtest" ? "Backtest" : "Strategy Lab"}</h2><p className="mt-2 max-w-5xl text-sm text-stone-600">{standaloneTab === "Replay" ? "Practise historical markets candle-by-candle without revealing the future; Replay trades feed directly into Journal." : "Backtest coded strategy plugins with explicit execution rules, saved reproducible runs, validation and diagnostic analysis."}</p></div>
    {!standaloneTab && <div className="mt-6 flex gap-6 border-b border-stone-200">{["Backtest","Validation","Runs","Strategies","Indicators","Strategy Workspace","Replay"].map((item) => <button key={item} onClick={() => { setTab(item); if (item === "Runs") refreshRuns(); }} className={`border-b-2 px-1 pb-3 text-sm ${tab === item ? "border-stone-900 font-medium" : "border-transparent text-stone-500"}`}>{item}</button>)}</div>}
    {standaloneTab === "Backtest" && <div className="mt-5 flex flex-wrap gap-2">{["Backtest","Validation","Runs","Strategies","Indicators","Strategy Workspace"].map(item=><button key={item} onClick={()=>{setTab(item);if(item==="Runs")refreshRuns()}} className={`mini-btn ${tab===item?"active-btn":""}`}>{item}</button>)}</div>}
    {error && <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}

    {tab === "Backtest" && <>
      <section className="mt-5 rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
        <div className="grid gap-6 xl:grid-cols-[1.15fr_.85fr]">
          <div>
            <h3 className="font-semibold">Test definition</h3>
            <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Field label="Strategy"><select className="input" value={strategyKey} onChange={(e) => setStrategyKey(e.target.value)}>{strategies.map((item) => <option key={item.key} value={item.key}>{item.name}</option>)}</select></Field>
              <Field label="Start date"><input type="date" className="input" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></Field>
              <Field label="End date"><input type="date" className="input" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></Field>
              <Field label="Primary timeframe"><select className="input" value={form.primary_timeframe} onChange={(e) => setForm({ ...form, primary_timeframe: e.target.value })}>{timeframes.map((tf) => <option key={tf}>{tf}</option>)}</select></Field>
              <Field label="Market data session"><select className="input" value={form.session} onChange={(e) => updateSession(e.target.value)}><option value="auto">Auto · match instrument</option><option value="24h">24h / full provider session</option><option value="regular">US regular · 09:30–16:00 ET</option><option value="extended">US extended · 04:00–20:00 ET</option></select></Field>
              <Field label="Same-bar stop + target"><select className="input" value={form.same_bar_policy} onChange={(e) => setForm({ ...form, same_bar_policy: e.target.value })}><option value="stop_first">Stop first · conservative</option><option value="target_first">Target first · sensitivity test</option></select></Field>
            </div>
            <div className="mt-4"><span className="mb-1 block text-xs font-medium text-stone-500">Symbols</span><div className="flex flex-wrap gap-2">{symbols.map((symbol) => <button key={symbol} type="button" onClick={() => setSymbols((old) => old.filter((x) => x !== symbol))} className="rounded-full border border-stone-300 bg-stone-50 px-3 py-1 text-xs font-mono">{symbol} ×</button>)}</div><div className="mt-2 max-w-md"><SymbolSearch value={symbolInput} onChange={setSymbolInput} onSelect={(item) => addSymbol(item.ticker)} placeholder="Add ticker…" /></div><button type="button" onClick={() => addSymbol()} className="mt-2 text-xs font-medium text-stone-600 underline">Add typed symbol</button></div>
          </div>
          <div>
            <h3 className="font-semibold">Account sizing & execution</h3><p className="mt-1 text-xs text-stone-500">Controls how large positions are and how fills/costs are simulated. Stop, target and management rules belong to the selected strategy.</p>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <Field label="Starting balance"><NumberInput value={form.starting_balance} onChange={(v) => setForm({ ...form, starting_balance: v })} /></Field>
              <Field label="Sizing mode"><select className="input" value={form.sizing_mode} onChange={(e) => setForm({ ...form, sizing_mode: e.target.value })}><option value="risk_pct">Risk % of account</option><option value="cash_risk">Fixed cash risk</option><option value="quantity">Fixed share quantity</option><option value="cash_position">Fixed cash position</option><option value="position_pct">Position % of account</option></select></Field>
              <Field label={sizingLabel(form.sizing_mode)}><NumberInput value={form.risk_value} onChange={(v) => setForm({ ...form, risk_value: v })} /></Field>
              <Field label="Max leverage"><NumberInput value={form.max_leverage} onChange={(v) => setForm({ ...form, max_leverage: v })} /></Field>
              <Field label="Commission / order"><NumberInput value={form.commission_per_order} onChange={(v) => setForm({ ...form, commission_per_order: v })} /></Field>
              <Field label="Slippage (bps)"><NumberInput value={form.slippage_bps} onChange={(v) => setForm({ ...form, slippage_bps: v })} /></Field>
              <Field label="Assumed full spread (bps)"><NumberInput value={form.spread_bps} onChange={(v) => setForm({ ...form, spread_bps: v })} /></Field>
              <Field label="Max open positions"><NumberInput value={form.max_open_positions} onChange={(v) => setForm({ ...form, max_open_positions: v })} /></Field>
            </div>
          </div>
        </div>

        <div className="mt-6 border-t border-stone-100 pt-5">
          <h3 className="font-semibold">Trading schedule</h3><p className="mt-1 text-xs text-stone-500">No entry window means all loaded market hours are eligible. Optional windows use New York / ET, start-inclusive and end-exclusive. This is separate from the market-data session above.</p>
          <div className="mt-4 grid gap-5 lg:grid-cols-[1.3fr_.7fr]">
            <div><p className="text-xs font-medium text-stone-500">Allowed entry windows <span className="font-normal">(optional)</span></p>{!entryWindows.length && <p className="mt-2 text-xs text-stone-400">None · entries may occur at any loaded market time.</p>}<div className="mt-2 space-y-2">{entryWindows.map((window, index) => <div key={index} className="flex max-w-xl items-center gap-2"><input type="time" className="input" value={window.start} onChange={(e) => setEntryWindows((old) => old.map((w,i) => i === index ? { ...w, start: e.target.value } : w))} /><span className="text-xs text-stone-500">to</span><input type="time" className="input" value={window.end} onChange={(e) => setEntryWindows((old) => old.map((w,i) => i === index ? { ...w, end: e.target.value } : w))} />{entryWindows.length > 1 && <button type="button" onClick={() => setEntryWindows((old) => old.filter((_,i) => i !== index))} className="px-2 text-xs text-red-700">Remove</button>}</div>)}</div><button type="button" onClick={() => setEntryWindows((old) => [...old, { start: "09:30", end: "16:00" }])} className="mt-2 text-xs font-medium text-stone-600 underline">+ Add another window</button></div>
            <div><p className="text-xs font-medium text-stone-500">Trading days</p><div className="mt-2 flex flex-wrap gap-2">{weekdays.map(([value,label]) => <button type="button" key={value} onClick={() => setSelectedWeekdays((old) => old.includes(value) ? old.filter((x) => x !== value) : [...old, value].sort())} className={`rounded-md border px-3 py-2 text-xs ${selectedWeekdays.includes(value) ? "border-stone-900 bg-stone-900 text-white" : "border-stone-300 bg-white text-stone-600"}`}>{label}</button>)}</div><div className="mt-4 grid gap-3 sm:grid-cols-2"><Field label="Hold overnight?"><select className="input" value={form.allow_overnight} onChange={(e) => setForm({ ...form, allow_overnight: e.target.value })}><option value="false">No · flatten same day</option><option value="true">Yes · allow overnight</option></select></Field>{form.allow_overnight === "false" && <Field label="Force close time (ET)"><input type="time" className="input" value={form.force_close_time} onChange={(e) => setForm({ ...form, force_close_time: e.target.value })} /></Field>}</div></div>
          </div>
        </div>

        <div className="mt-5 border-t border-stone-100 pt-4"><button type="button" onClick={() => setShowAdvanced((v) => !v)} className="text-sm font-medium text-stone-700 underline">{showAdvanced ? "Hide" : "Show"} session guardrails</button>{showAdvanced && <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4"><Field label="Max trades / day"><OptionalNumberInput value={form.max_trades_per_day} onChange={(v) => setForm({ ...form, max_trades_per_day: v })} placeholder="No limit" /></Field><Field label="Stop after daily loss (R)"><OptionalNumberInput value={form.max_daily_loss_r} onChange={(v) => setForm({ ...form, max_daily_loss_r: v })} placeholder="No limit" /></Field><Field label="Stop after consecutive losses"><OptionalNumberInput value={form.max_consecutive_losses} onChange={(v) => setForm({ ...form, max_consecutive_losses: v })} placeholder="No limit" /></Field><Field label="Cooldown after exit (minutes)"><NumberInput value={form.cooldown_minutes} onChange={(v) => setForm({ ...form, cooldown_minutes: v })} /></Field></div>}</div>

        {strategy && <div className="mt-6 border-t border-stone-100 pt-5"><div className="flex flex-wrap items-baseline justify-between gap-2"><div><h3 className="font-semibold">Strategy parameters</h3><p className="mt-1 text-xs text-stone-500">{strategy.description}</p></div><span className="rounded bg-amber-50 px-2 py-1 text-[11px] text-amber-800">Reference strategy ≠ proven edge</span></div><div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{(strategy.parameters || []).map((parameter) => <ParameterField key={parameter.key} parameter={parameter} value={params[parameter.key]} onChange={(value) => setParams({ ...params, [parameter.key]: value })} />)}</div>{strategy.risk_management && Object.keys(strategy.risk_management).length > 0 && <div className="mt-5 rounded-lg border border-stone-200 bg-stone-50 p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Strategy-owned risk management</p><p className="mt-1 text-xs text-stone-600">Stop, target and position-management rules come from the strategy code. The run controls only decide account sizing, costs, schedule and guardrails.</p></div>{strategy.source_file && <code className="rounded bg-white px-2 py-1 text-[11px] text-stone-500">{strategy.source_file}</code>}</div><div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{Object.entries(strategy.risk_management).map(([label, value]) => <div key={label} className="rounded-md bg-white px-3 py-2"><div className="text-[10px] uppercase tracking-wide text-stone-400">{label}</div><div className="mt-1 text-xs font-medium text-stone-700">{value}</div></div>)}</div></div>}</div>}

        <div className="mt-6 grid gap-4 border-t border-stone-100 pt-5 lg:grid-cols-4"><Field label="Run name (optional)"><input className="input" value={runMeta.name} onChange={(e) => setRunMeta({ ...runMeta, name: e.target.value })} placeholder="e.g. EMA baseline · no overnight" /></Field><Field label="Research role"><select className="input" value={runMeta.test_role} onChange={(e) => setRunMeta({ ...runMeta, test_role: e.target.value })}>{roles.map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></Field><Field label="Tags (comma separated)"><input className="input" value={runMeta.tags} onChange={(e) => setRunMeta({ ...runMeta, tags: e.target.value })} placeholder="baseline, AAPL, 5m" /></Field><Field label="Run notes (optional)"><input className="input" value={runMeta.notes} onChange={(e) => setRunMeta({ ...runMeta, notes: e.target.value })} placeholder="What hypothesis is this run testing?" /></Field></div>
        {runMeta.test_role === "out_of_sample" && <p className="mt-2 text-xs text-amber-800">Out-of-sample data is most useful when you avoid repeatedly tuning rules against it. Ledger labels the run but does not prevent you from reusing the period.</p>}
        <div className="mt-5 flex items-center justify-between gap-4 rounded-lg bg-stone-50 p-4"><p className="text-xs text-stone-600"><strong>No-lookahead contract:</strong> strategy evaluates after a candle completes; entries/discretionary exits fill next bar open. Every successful run is saved as an immutable result snapshot for later comparison.</p><button disabled={loading || !symbols.length || !selectedWeekdays.length} onClick={run} className="shrink-0 rounded-md bg-stone-900 px-5 py-2.5 text-sm font-medium text-white disabled:opacity-50">{loading ? "Fetching data / testing…" : "Run backtest"}</button></div>
      </section>
      {result && <BacktestResults result={result} />}
    </>}

    {tab === "Validation" && <ValidationPanel buildPayload={buildPayload} startDate={form.start_date} endDate={form.end_date} strategyName={strategy?.name || strategyKey} strategy={strategy} refreshRuns={refreshRuns} onError={setError} savedExperiment={savedExperiment} onClearSavedExperiment={() => setSavedExperiment(null)} />}
    {tab === "Runs" && <RunsPanel runs={runs} onRefresh={refreshRuns} onOpen={openSavedRun} onUseSettings={useSavedSettings} onOpenExperiment={openSavedExperiment} />}
    {tab === "Strategies" && <section className="mt-5 grid gap-4 lg:grid-cols-2">{strategies.map((item) => <div key={item.key} className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm"><div className="flex items-start justify-between gap-3"><div><p className="text-xs uppercase tracking-wide text-stone-500">{item.category}</p><h3 className="mt-1 font-semibold">{item.name}</h3></div><code className="rounded bg-stone-100 px-2 py-1 text-xs">{item.key}</code></div><p className="mt-3 text-sm text-stone-600">{item.description}</p><p className="mt-3 text-xs text-stone-500">Default timeframe: {(item.timeframes || []).join(", ")}</p><p className="mt-2 text-xs text-stone-500">Strategy code owns entry, initial stop/target and next-bar position management (including breakeven, trailing rules and partial exits). The run screen owns account sizing, execution costs, schedule and account guardrails.</p>{item.risk_management && Object.keys(item.risk_management).length > 0 && <div className="mt-3 rounded-lg bg-stone-50 p-3 text-xs text-stone-600">{Object.entries(item.risk_management).map(([label,value]) => <div key={label} className="mt-1"><strong>{label}:</strong> {value}</div>)}</div>}{(item.research_parameters || []).length > 0 && <p className="mt-3 text-xs text-stone-500"><strong>Research-only sensitivity:</strong> {(item.research_parameters || []).map((p) => p.label).join(", ")}. These do not appear on ordinary runs.</p>}</div>)}</section>}
    {tab === "Indicators" && <section className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{indicators.map((item) => <div key={item.key} className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm"><div className="flex items-center justify-between"><h3 className="font-semibold">{item.name}</h3><code className="rounded bg-stone-100 px-2 py-1 text-xs">{item.key}</code></div><p className="mt-3 text-sm text-stone-600">{item.overlay ? "Price-chart overlay" : "Separate/pane indicator"}</p><p className="mt-2 text-xs text-stone-500">Defaults: {Object.entries(item.defaults || {}).map(([k,v]) => `${k}=${v}`).join(", ") || "None"}</p></div>)}</section>}
    {standaloneTab !== "Replay" && <div hidden={tab !== "Strategy Workspace"}><StrategyWorkspace onDirtyChange={onWorkspaceDirty} onResult={response=>{setResult(response);refreshRuns();}} /></div>}
    {tab === "Replay" && <ReplayPanel indicators={indicators} onError={setError} />}
  </div>;
}

function BacktestResults({ result }) {
  const m = result.metrics || {};
  const [filters, setFilters] = useState({ symbol: "all", direction: "all", result: "all", exit_reason: "all" });
  const [auditTrade, setAuditTrade] = useState(null);
  const [performanceMode, setPerformanceMode] = useState("equity");
  const [chartZone, setChartZone] = useState("America/New_York");
  const [expandedChart, setExpandedChart] = useState(null);
  const trades = result.trades || [];
  const filtered = useMemo(() => trades.filter((trade) =>
    (filters.symbol === "all" || trade.symbol === filters.symbol) &&
    (filters.direction === "all" || trade.direction === filters.direction) &&
    (filters.result === "all" || trade.result === filters.result) &&
    (filters.exit_reason === "all" || trade.exit_reason === filters.exit_reason)
  ), [trades, filters]);
  const exitReasons = [...new Set(trades.map((trade) => trade.exit_reason))].sort();
  const openEventTrade = useCallback((event) => {
    const match = trades.find((trade) => trade.symbol === event.symbol && trade.exit_time === event.exit_time) || trades.find((trade) => trade.symbol === event.symbol && trade.exit_reason === event.exit_reason);
    if (match) { setExpandedChart(null); setAuditTrade(match); }
  }, [trades]);

  return <>
    {(result.data?.warnings || []).map((warning) => <p key={warning} className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">{warning}</p>)}
    {result.data?.portfolio_scope && <p className="mt-3 text-xs text-stone-600">{result.data.portfolio_scope}</p>}
    {result.saved_run && <div className="mt-5 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs text-emerald-800">Saved as run <strong>#{result.saved_run.id}</strong>{result.saved_run.name ? ` · ${result.saved_run.name}` : ""} · {String(result.saved_run.test_role || "development").replaceAll("_", " ")}. Open the <strong>Runs</strong> tab later without re-running it.</div>}
    <section className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
      <Stat label="Starting balance" value={money(m.starting_balance)} /><Stat label="Ending balance" value={money(m.ending_balance)} /><Stat label="Net P&L" value={money(m.net_pnl)} /><Stat label="Return" value={pct(m.return_pct)} /><Stat label="Trades" value={m.trades ?? "—"} />{result.setup_metrics && <><Stat label="Setups" value={result.setup_metrics.setups ?? "—"} /><Stat label="Entry fill rate" value={pct(result.setup_metrics.entry_fill_rate_pct)} /></>}<Stat label="Win rate" value={pct(m.win_rate_pct)} /><Stat label="Expectancy" value={r(m.expectancy_r)} /><Stat label="Total R" value={r(m.total_r)} /><Stat label="Avg planned R:R" value={m.average_planned_rr == null ? "—" : `${number(m.average_planned_rr)}:1`} /><Stat label="Profit factor (R)" value={number(m.profit_factor_r)} /><Stat label="Max drawdown" value={pct(m.max_drawdown_pct)} /><Stat label="Longest losing streak" value={m.longest_losing_streak ?? "—"} />
    </section>

    <section className="mt-5 rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-semibold">Performance</h3><p className="mt-1 text-xs text-stone-500">Hover for exact values. Closed trades are marked explicitly; click a trade marker to open that exact historical chart audit.</p></div><div className="flex flex-wrap items-end gap-2"><Field label="Timezone"><select className="input min-w-[190px]" value={chartZone} onChange={(e) => setChartZone(e.target.value)}>{TIMEZONE_OPTIONS.map((zone) => <option key={zone.value} value={zone.value}>{zone.label}</option>)}</select></Field><span className="pb-2 text-xs text-stone-500">Data: {String(result.data?.feed || "—").toUpperCase()} · adjustment {result.data?.adjustment || "—"}</span></div></div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3"><div className="flex gap-2">{[["equity","Equity $"],["return","Return %"],["r","Cumulative R"]].map(([key,label]) => <button key={key} onClick={() => setPerformanceMode(key)} className={`rounded-md border px-3 py-2 text-xs ${performanceMode === key ? "border-stone-900 bg-stone-900 text-white" : "border-stone-300"}`}>{label}</button>)}</div><button onClick={() => setExpandedChart("performance")} className="rounded-md border border-stone-300 px-3 py-2 text-xs font-medium">Expand performance</button></div>
      <PerformanceChart points={result.equity_curve || []} startingBalance={m.starting_balance} mode={performanceMode} timeZone={chartZone} onTradeSelect={openEventTrade} />
      <div className="mt-6 border-t border-stone-100 pt-5"><div className="flex items-center justify-between gap-3"><div><h4 className="text-sm font-semibold">Drawdown</h4><p className="mt-1 text-xs text-stone-500">Peak-to-trough equity decline over the run.</p></div><button onClick={() => setExpandedChart("drawdown")} className="rounded-md border border-stone-300 px-3 py-2 text-xs font-medium">Expand drawdown</button></div><PerformanceChart points={result.equity_curve || []} startingBalance={m.starting_balance} mode="drawdown" timeZone={chartZone} onTradeSelect={openEventTrade} /></div>
    </section>

    {expandedChart && <div className="fixed inset-3 z-40 overflow-auto rounded-xl border border-stone-300 bg-white p-5 shadow-2xl"><div className="flex items-start justify-between gap-3"><div><h3 className="text-lg font-semibold">{expandedChart === "drawdown" ? "Drawdown" : performanceMode === "equity" ? "Equity" : performanceMode === "return" ? "Return" : "Cumulative R"}</h3><p className="mt-1 text-xs text-stone-500">{TIMEZONE_OPTIONS.find((item) => item.value === chartZone)?.label || chartZone}</p></div><button onClick={() => setExpandedChart(null)} className="rounded-md border border-stone-300 px-3 py-2 text-xs font-medium">Close expanded chart</button></div><PerformanceChart points={result.equity_curve || []} startingBalance={m.starting_balance} mode={expandedChart === "drawdown" ? "drawdown" : performanceMode} timeZone={chartZone} expanded onTradeSelect={openEventTrade} /></div>}

    {result.strategy?.key === "momentum_vcp_breakout_baseline_v1" && <section className="mt-5 rounded-xl border border-stone-200 bg-white p-5">
      <h3 className="font-semibold">Detected breakout setups</h3>
      <p className="mt-1 text-xs text-stone-500">All qualifying breakouts, including entries rejected at the next open. Setup counts are separate from portfolio performance.</p>
      {!(result.setups || []).length && <p className="mt-3 text-sm">No qualifying setups in the completed data after warm-up.</p>}
      {(result.setups || []).map((setup, index) => <details key={`${setup.symbol}-${setup.detected_at}-${index}`} className="mt-3 rounded-lg border border-stone-200 p-3">
        <summary className="cursor-pointer text-sm"><strong>{setup.symbol}</strong> · {setup.metadata?.breakout_date} · {setup.status.replaceAll("_", " ")}{setup.resolution_reason ? ` · ${setup.resolution_reason.replaceAll("_", " ")}` : ""}</summary>
        <dl className="mt-3 grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">{Object.entries({ ...setup.metadata, ...setup.outcome }).filter(([, value]) => typeof value !== "object" || value === null).map(([key, value]) => <div key={key} className="min-w-0"><dt className="text-stone-500">{key.replaceAll("_", " ")}</dt><dd className="break-words">{value == null ? "—" : typeof value === "number" ? number(value) : String(value)}</dd></div>)}</dl>
      </details>)}
    </section>}
    <AnalysisPanel analysis={result.analysis || {}} />
    {auditTrade && <TradeAuditChart trade={auditTrade} timeframe={result.primary_timeframe} session={result.session} onClose={() => setAuditTrade(null)} />}

    <section className="mt-5 overflow-hidden rounded-xl border border-stone-200 bg-white shadow-sm">
      <div className="border-b border-stone-100 px-5 py-4"><div className="flex flex-wrap items-start justify-between gap-4"><div><h3 className="font-semibold">Simulated trades</h3><p className="mt-1 text-xs text-stone-500">Filter results and open any trade on the underlying historical chart to audit the engine.</p></div><span className="text-xs text-stone-500">Showing {filtered.length} of {trades.length}</span></div><div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><FilterSelect label="Symbol" value={filters.symbol} onChange={(value) => setFilters({ ...filters, symbol: value })} options={["all", ...(result.symbols || [])]} /><FilterSelect label="Direction" value={filters.direction} onChange={(value) => setFilters({ ...filters, direction: value })} options={["all","long","short"]} /><FilterSelect label="Result" value={filters.result} onChange={(value) => setFilters({ ...filters, result: value })} options={["all","win","loss","breakeven"]} /><FilterSelect label="Exit reason" value={filters.exit_reason} onChange={(value) => setFilters({ ...filters, exit_reason: value })} options={["all", ...exitReasons]} /></div></div>
      <div className="overflow-x-auto"><table className="w-full min-w-[1500px] text-sm"><thead className="bg-stone-50 text-xs uppercase tracking-wide text-stone-500"><tr>{["Symbol","Direction","Entry time (ET)","Entry","Stop","Target","Exit time (ET)","Exit","Exit reason","Planned R:R","Realised R","Net P&L","Result","Audit"].map((h) => <th key={h} className="px-3 py-3 text-left">{h}</th>)}</tr></thead><tbody className="divide-y divide-stone-100">{filtered.map((trade, index) => <tr key={`${trade.symbol}-${trade.entry_time}-${index}`}><td className="px-3 py-3 font-mono font-semibold">{trade.symbol}</td><td className="px-3 py-3">{trade.direction}</td><td className="whitespace-nowrap px-3 py-3">{formatDate(trade.entry_time)}</td><td className="px-3 py-3">{number(trade.entry_price)}</td><td className="px-3 py-3">{number(trade.stop_loss)}</td><td className="px-3 py-3">{number(trade.take_profit)}</td><td className="whitespace-nowrap px-3 py-3">{formatDate(trade.exit_time)}</td><td className="px-3 py-3">{number(trade.exit_price)}</td><td className="px-3 py-3 text-xs text-stone-500">{trade.exit_reason}</td><td className="px-3 py-3">{trade.planned_rr == null ? "—" : `${number(trade.planned_rr)}:1`}</td><td className="px-3 py-3">{r(trade.r_multiple)}</td><td className={`px-3 py-3 ${Number(trade.net_pnl) >= 0 ? "text-emerald-700" : "text-red-700"}`}>{money(trade.net_pnl)}</td><td className={`px-3 py-3 font-medium ${trade.result === "win" ? "text-emerald-700" : trade.result === "loss" ? "text-red-700" : ""}`}>{trade.result.toUpperCase()}</td><td className="px-3 py-3"><button onClick={() => setAuditTrade(trade)} className="text-xs font-medium underline">View chart</button></td></tr>)}</tbody></table></div>
      {!filtered.length && <p className="p-8 text-center text-sm text-stone-500">No trades match these filters.</p>}
    </section>
    <section className="mt-5 rounded-xl border border-stone-200 bg-stone-50 p-4 text-xs text-stone-600"><strong>Execution assumptions:</strong> signal {result.execution_model?.signal_timing?.replaceAll("_", " ")} → fill {result.execution_model?.entry_timing?.replaceAll("_", " ")}; same-bar policy {result.execution_model?.same_bar_policy?.replaceAll("_", " ")}; stop gaps {result.execution_model?.stop_gap_policy?.replaceAll("_", " ")}; overnight {result.execution_model?.allow_overnight ? "allowed" : `disabled · flatten ${result.execution_model?.force_close_time} ET`}. Rejected entry signals: {(result.rejected_signals || []).length}.{(result.rejected_signal_summary || []).length > 0 && <span className="ml-1">{(result.rejected_signal_summary || []).map((item) => `${String(item.reason).replaceAll("_", " ")} (${item.count})`).join(" · ")}</span>}</section>
  </>;
}

function RunsPanel({ runs, onRefresh, onOpen, onUseSettings, onOpenExperiment }) {
  const [selected, setSelected] = useState([]);
  const [view, setView] = useState("all");
  const toggle = (id) => setSelected((old) => old.includes(id) ? old.filter((x) => x !== id) : old.length >= 12 ? old : [...old, id]);
  const compared = selected.map((id) => runs.find((run) => run.id === id)).filter(Boolean);
  const experimentGroups = Object.entries(runs.reduce((groups, run) => {
    if (!run.experiment_group || (run.tags || []).includes("sensitivity")) return groups;
    (groups[run.experiment_group] ||= []).push(run);
    return groups;
  }, {})).filter(([, items]) => new Set(items.map((item) => item.test_role)).size >= 2);
  const sensitivityRuns = runs.filter((run) => (run.tags || []).includes("sensitivity") || String(run.experiment_group || "").startsWith("sensitivity-"));
  const visibleRuns = view === "sensitivity" ? sensitivityRuns : runs;
  const remove = async (id) => { if (!window.confirm(`Delete saved backtest run #${id}?`)) return; await api.deleteStrategyLabRun(id); setSelected((old) => old.filter((x) => x !== id)); onRefresh(); };

  return <section className="mt-5 rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
    <div className="flex items-start justify-between gap-4"><div><h3 className="font-semibold">Saved backtest research</h3><p className="mt-1 max-w-4xl text-xs text-stone-500">Runs, validation suites and sensitivity experiments are separated so validation cards do not permanently consume the Runs screen.</p></div><button onClick={onRefresh} className="rounded-md border border-stone-300 px-3 py-2 text-xs">Refresh</button></div>
    {runs.some((run) => run.strategy_key === "momentum_vcp_breakout_baseline_v1") && <p className="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-900">Momentum stock runs: Historical universe may contain survivorship bias.</p>}
    <div className="mt-4 flex gap-2">{[["all","All runs"],["validation","Validation suites"],["sensitivity","Sensitivity"]].map(([key,label]) => <button key={key} onClick={() => setView(key)} className={`rounded-md border px-3 py-2 text-xs ${view === key ? "border-stone-900 bg-stone-900 text-white" : "border-stone-300 bg-white"}`}>{label}</button>)}</div>
    {compared.length >= 2 && view !== "validation" && <RunComparison ids={compared.map(run => run.id)} />}
    {view === "validation" && <div className="mt-5">
      {!experimentGroups.length && <p className="rounded-lg bg-stone-50 p-6 text-center text-sm text-stone-500">No saved validation suites yet.</p>}
      <div className="grid gap-3 xl:grid-cols-2">{experimentGroups.map(([group, items]) => <ExperimentSummary key={group} group={group} items={items} onOpen={onOpen} onOpenExperiment={onOpenExperiment} />)}</div>
    </div>}
    {view !== "validation" && <div className="mt-4 overflow-x-auto rounded-lg border border-stone-200"><table className="w-full min-w-[1250px] text-sm"><thead className="bg-stone-50 text-xs uppercase tracking-wide text-stone-500"><tr>{["Compare","Run","Role","Experiment","Tags","Created","Strategy","Symbols","Period","TF","Trades","Expectancy","Total R","Return","Max DD","Actions"].map((head) => <th key={head} className="px-3 py-3 text-left">{head}</th>)}</tr></thead><tbody className="divide-y divide-stone-100">{visibleRuns.map((run) => <tr key={run.id}><td className="px-3 py-3"><input type="checkbox" checked={selected.includes(run.id)} onChange={() => toggle(run.id)} /></td><td className="px-3 py-3"><div className="font-semibold">#{run.id} {run.name || "Untitled run"}</div></td><td className="px-3 py-3 text-xs"><RoleBadge role={run.test_role} /></td><td className="max-w-[180px] truncate px-3 py-3 text-xs" title={run.experiment_group || ""}>{run.experiment_group || "—"}</td><td className="px-3 py-3 text-xs">{(run.tags || []).join(", ") || "—"}</td><td className="whitespace-nowrap px-3 py-3 text-xs">{run.created_at}</td><td className="px-3 py-3">{run.strategy_name}</td><td className="px-3 py-3 font-mono text-xs">{(run.symbols || []).join(", ")}</td><td className="whitespace-nowrap px-3 py-3 text-xs">{run.start_date} → {run.end_date}</td><td className="px-3 py-3">{run.primary_timeframe}</td><td className="px-3 py-3">{run.trades}</td><td className="px-3 py-3">{r(run.expectancy_r)}</td><td className="px-3 py-3">{r(run.total_r)}</td><td className="px-3 py-3">{pct(run.return_pct)}</td><td className="px-3 py-3">{pct(run.max_drawdown_pct)}</td><td className="whitespace-nowrap px-3 py-3 text-xs"><button onClick={() => onOpen(run.id)} className="mr-3 font-medium underline">Open</button><button onClick={() => onUseSettings(run.id)} className="mr-3 font-medium underline">Use settings</button><button onClick={() => remove(run.id)} className="text-red-700 underline">Delete</button></td></tr>)}</tbody></table></div>}
    {view !== "validation" && !visibleRuns.length && <p className="p-8 text-center text-sm text-stone-500">{view === "sensitivity" ? "No sensitivity runs yet." : "No saved runs yet. Your next successful backtest will appear here automatically."}</p>}
  </section>;
}
function RoleBadge({ role }) {
  const key = String(role || "unclassified");
  const classes = key === "development" ? "bg-blue-50 text-blue-800 border-blue-200" : key === "validation" ? "bg-amber-50 text-amber-800 border-amber-200" : key === "out_of_sample" ? "bg-purple-50 text-purple-800 border-purple-200" : "bg-stone-50 text-stone-700 border-stone-200";
  return <span className={`inline-flex rounded-full border px-2 py-1 text-[11px] font-medium ${classes}`}>{key.replaceAll("_", " ")}</span>;
}
function ExperimentSummary({ group, items, onOpen, onOpenExperiment }) {
  const ordered = ["development", "validation", "out_of_sample"].map((role) => items.find((item) => item.test_role === role)).filter(Boolean);
  return <div className="rounded-lg border border-stone-200 bg-stone-50 p-4"><div className="flex items-start justify-between gap-3"><div><p className="text-xs uppercase tracking-wide text-stone-500">Experiment</p><p className="mt-1 max-w-[420px] truncate text-sm font-semibold" title={group}>{group}</p></div><span className="text-xs text-stone-500">{items.length} runs</span></div><button onClick={() => onOpenExperiment(group)} className="mt-3 w-full rounded-md bg-stone-900 px-3 py-2 text-xs font-medium text-white">Open full validation experiment</button><div className="mt-3 space-y-2">{ordered.map((run) => <button key={run.id} onClick={() => onOpen(run.id)} className="grid w-full grid-cols-[120px_1fr_80px_80px] items-center gap-2 rounded-md bg-white px-3 py-2 text-left text-xs hover:bg-stone-100"><RoleBadge role={run.test_role} /><span>{run.start_date} → {run.end_date}</span><span className="text-right">{r(run.expectancy_r)}</span><span className="text-right">{pct(run.max_drawdown_pct)}</span></button>)}</div></div>;
}

function AnalysisPanel({ analysis }) {
  const [breakdown, setBreakdown] = useState("entry_hour");
  const rows = analysis.breakdowns?.[breakdown] || [];
  const labelMap = { session: "Session", entry_hour: "Entry time", weekday: "Weekday", direction: "Direction", symbol: "Symbol", month: "Month", exit_reason: "Exit reason", signal_reason: "Signal reason" };
  return <section className="mt-5 rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
    <div><h3 className="font-semibold">Why is it working / not working?</h3><p className="mt-1 max-w-4xl text-xs text-stone-500">Descriptive diagnostics split the same run by time, day, direction, symbol and exit type. Use them to form hypotheses, then validate those hypotheses on unseen data.</p></div>
    {(analysis.observations || []).length > 0 && <div className="mt-4 grid gap-3 lg:grid-cols-2">{analysis.observations.map((item, index) => <div key={`${item.kind}-${index}`} className="rounded-lg bg-stone-50 p-4"><p className="text-xs font-semibold uppercase tracking-wide text-stone-500">{item.title}</p><p className="mt-2 text-sm text-stone-700">{item.text}</p></div>)}</div>}
    <div className="mt-5 flex flex-wrap gap-2">{Object.keys(labelMap).map((key) => <button key={key} onClick={() => setBreakdown(key)} className={`rounded-md border px-3 py-2 text-xs ${breakdown === key ? "border-stone-900 bg-stone-900 text-white" : "border-stone-300 bg-white"}`}>{labelMap[key]}</button>)}</div>
    <div className="mt-3 overflow-x-auto rounded-lg border border-stone-200"><table className="w-full min-w-[760px] text-sm"><thead className="bg-stone-50 text-xs uppercase tracking-wide text-stone-500"><tr><th className="px-3 py-2 text-left">{labelMap[breakdown]}</th><th className="px-3 py-2 text-right">Trades</th><th className="px-3 py-2 text-right">Win rate</th><th className="px-3 py-2 text-right">Avg R</th><th className="px-3 py-2 text-right">Total R</th><th className="px-3 py-2 text-right">PF (R)</th><th className="px-3 py-2 text-right">Net P&L</th></tr></thead><tbody className="divide-y divide-stone-100">{rows.map((row, index) => { const key = row[breakdown]; return <tr key={`${key}-${index}`}><td className="px-3 py-2 font-medium">{String(key || "—").replaceAll("_", " ")}</td><td className="px-3 py-2 text-right">{row.trades}</td><td className="px-3 py-2 text-right">{pct(row.win_rate_pct)}</td><td className="px-3 py-2 text-right">{r(row.average_r)}</td><td className="px-3 py-2 text-right">{r(row.total_r)}</td><td className="px-3 py-2 text-right">{number(row.profit_factor_r)}</td><td className={`px-3 py-2 text-right ${Number(row.net_pnl) >= 0 ? "text-emerald-700" : "text-red-700"}`}>{money(row.net_pnl)}</td></tr>; })}</tbody></table></div>
    {(analysis.largest_losses || []).length > 0 && <div className="mt-5 border-t border-stone-100 pt-4"><h4 className="text-sm font-semibold">Largest realised losses</h4><p className="mt-1 text-xs text-stone-500">Useful for spotting gap risk, execution assumptions or one-off events that dominate the sample.</p><div className="mt-3 grid gap-2 lg:grid-cols-2">{(analysis.largest_losses || []).map((trade, index) => <div key={`${trade.symbol}-${trade.exit_time}-${index}`} className="flex items-center justify-between rounded-lg bg-stone-50 px-3 py-2 text-xs"><span><strong>{trade.symbol}</strong> · {formatDate(trade.entry_time)} · {String(trade.exit_reason).replaceAll("_", " ")}</span><span className="font-semibold text-red-700">{r(trade.r_multiple)} · {money(trade.net_pnl)}</span></div>)}</div></div>}
    <p className="mt-3 text-xs text-amber-800">{analysis.note || "Historical breakdowns are descriptive, not validation."}</p>
  </section>;
}

function ParameterField({ parameter, value, onChange }) {
  if (parameter.kind === "choice") return <Field label={parameter.label}><select className="input" value={value ?? parameter.default} onChange={(e) => onChange(e.target.value)}>{(parameter.choices || []).map((choice) => <option key={choice} value={choice}>{choice}</option>)}</select></Field>;
  if (parameter.kind === "bool") return <Field label={parameter.label}><select className="input" value={String(value ?? parameter.default)} onChange={(e) => onChange(e.target.value === "true")}><option value="true">Yes</option><option value="false">No</option></select></Field>;
  return <Field label={parameter.label}><input className="input" type={parameter.kind === "string" ? "text" : "number"} min={parameter.minimum ?? undefined} max={parameter.maximum ?? undefined} step={parameter.step ?? "any"} value={value ?? parameter.default} onChange={(e) => onChange(e.target.value)} /></Field>;
}
function normaliseParams(strategy, params) { const result = {}; for (const p of strategy?.parameters || []) { const value = params[p.key]; result[p.key] = p.kind === "int" ? Number.parseInt(value,10) : p.kind === "float" ? Number(value) : p.kind === "bool" ? Boolean(value) : value; } return result; }
function optionalNumber(value) { return value === "" || value == null ? null : Number(value); }
function sizingLabel(mode) { if (mode === "risk_pct") return "Risk per trade (%)"; if (mode === "cash_risk") return "Cash risk per trade"; if (mode === "quantity") return "Shares per trade"; if (mode === "cash_position") return "Cash position size"; return "Position size (% of account)"; }
function NumberInput({ value, onChange }) { return <input type="number" step="any" className="input" value={value} onChange={(e) => onChange(e.target.value)} />; }
function OptionalNumberInput({ value, onChange, placeholder }) { return <input type="number" step="any" min="0" className="input" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />; }
function Field({ label, children }) { return <label className="block"><span className="mb-1 block text-xs font-medium text-stone-500">{label}</span>{children}</label>; }
function Stat({ label, value }) { return <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm"><p className="text-[11px] uppercase tracking-wide text-stone-500">{label}</p><p className="mt-2 text-lg font-semibold tabular-nums">{value}</p></div>; }
function FilterSelect({ label, value, onChange, options }) { return <Field label={label}><select className="input" value={value} onChange={(e) => onChange(e.target.value)}>{options.map((option) => <option key={option} value={option}>{option === "all" ? "All" : String(option).replaceAll("_", " ")}</option>)}</select></Field>; }
