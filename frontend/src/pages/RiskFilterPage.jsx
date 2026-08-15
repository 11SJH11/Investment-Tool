import { useState, useEffect, useRef } from "react";
import Card from "../components/Card";
import { api } from "../api";

const PRESET_LABELS = {
  low: "Low risk (capital preservation)",
  medium: "Medium risk (growth-tilted)",
  high: "High risk (day-trade momentum)",
};

export default function RiskFilterPage() {
  const [mode, setMode] = useState("low"); // "low" | "medium" | "high" | "custom"
  const [allCriteria, setAllCriteria] = useState([]); // from /api/risk-criteria
  const [presets, setPresets] = useState({});
  const [customSelection, setCustomSelection] = useState({}); // {key: value} for checked criteria in custom mode
  const [presetOverrides, setPresetOverrides] = useState({}); // {key: value} overrides for the active preset

  const [universes, setUniverses] = useState([]);
  const [universe, setUniverse] = useState("sp500");
  const [minPassed, setMinPassed] = useState("");

  const [jobId, setJobId] = useState(null);
  const [scanStatus, setScanStatus] = useState(null);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  useEffect(() => {
    api.getRiskCriteria().then((res) => {
      setAllCriteria(res.criteria);
      setPresets(res.presets);
    }).catch((e) => setError(e.message));
    api.getScanUniverses().then((res) => setUniverses(res.universes)).catch(() => {});
  }, []);

  useEffect(() => {
    // Reset per-preset override edits when switching mode
    setPresetOverrides({});
  }, [mode]);

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const toggleCustomCriterion = (key, defaultValue) => {
    setCustomSelection((prev) => {
      const next = { ...prev };
      if (key in next) delete next[key];
      else next[key] = defaultValue;
      return next;
    });
  };

  const updateCustomValue = (key, value) => {
    setCustomSelection((prev) => ({ ...prev, [key]: value }));
  };

  const updatePresetOverride = (key, value) => {
    setPresetOverrides((prev) => ({ ...prev, [key]: value }));
  };

  const runScan = async () => {
    setError(null);
    setScanStatus(null);
    if (pollRef.current) clearInterval(pollRef.current);

    try {
      let res;
      if (mode === "custom") {
        const criteria = Object.entries(customSelection).map(([key, value]) => ({ key, value: parseFloat(value) }));
        if (criteria.length === 0) {
          setError("Pick at least one criterion for a custom screen.");
          return;
        }
        res = await api.startScan(universe, "custom", null, minPassed ? parseInt(minPassed) : null, criteria);
      } else {
        res = await api.startScan(universe, mode, presetOverrides, minPassed ? parseInt(minPassed) : null);
      }
      setJobId(res.job_id);

      pollRef.current = setInterval(async () => {
        try {
          const status = await api.getScanStatus(res.job_id);
          setScanStatus(status);
          if (status.status === "done") clearInterval(pollRef.current);
        } catch (e) {
          setError(e.message);
          clearInterval(pollRef.current);
        }
      }, 1000);
    } catch (e) {
      setError(e.message);
    }
  };

  const progressPct = scanStatus ? Math.round((scanStatus.scanned / scanStatus.total) * 100) : 0;

  return (
    <div>
      <p className="font-body text-sm text-ink-soft mb-4 max-w-2xl">
        Scans an entire ticker universe and lists only what matches — you
        don't pick candidates yourself. This narrows a list for further
        research; it does not predict which stocks will actually perform
        well. Free data sources mean this can't cover literally every stock
        that exists — see the universe options below for what's realistically covered.
      </p>

      <Card eyebrow="Setup" title="Screen criteria" className="mb-6">
        <div className="flex items-center gap-3 mb-4 flex-wrap">
          {Object.entries(PRESET_LABELS).map(([key, label]) => (
            <label key={key} className="flex items-center gap-2 font-body text-sm">
              <input type="radio" checked={mode === key} onChange={() => setMode(key)} />
              {label}
            </label>
          ))}
          <label className="flex items-center gap-2 font-body text-sm">
            <input type="radio" checked={mode === "custom"} onChange={() => setMode("custom")} />
            Custom — pick your own
          </label>
        </div>

        {mode !== "custom" && presets[mode] && (
          <div className="mb-4">
            <p className="font-body text-xs text-ink-soft mb-2">
              Preset criteria — edit any value, or leave as default:
            </p>
            <div className="grid grid-cols-2 gap-x-6 gap-y-2">
              {presets[mode].criteria.map((c) => {
                const spec = allCriteria.find((ac) => ac.key === c.key);
                const currentVal = presetOverrides[c.key] ?? c.value;
                if (typeof c.value === "boolean") {
                  return (
                    <label key={c.key} className="flex items-center gap-2 font-body text-xs text-ink-soft">
                      <input
                        type="checkbox"
                        checked={!!currentVal}
                        onChange={(e) => updatePresetOverride(c.key, e.target.checked)}
                      />
                      {spec?.label.replace(/\{value\}/, "") || c.key}
                    </label>
                  );
                }
                return (
                  <label key={c.key} className="flex items-center justify-between gap-2">
                    <span className="font-body text-xs text-ink-soft">{spec?.label || c.key}</span>
                    <input
                      type="number"
                      value={currentVal}
                      onChange={(e) => updatePresetOverride(c.key, parseFloat(e.target.value))}
                      className="font-mono text-sm px-2 py-1 border border-line rounded-sm bg-white w-28"
                    />
                  </label>
                );
              })}
            </div>
          </div>
        )}

        {mode === "custom" && (
          <div className="mb-4">
            <p className="font-body text-xs text-ink-soft mb-2">
              Check any criteria you want, edit the value for each:
            </p>
            <div className="flex flex-col gap-2">
              {allCriteria.map((c) => {
                const checked = c.key in customSelection;
                return (
                  <div key={c.key} className="flex items-center gap-3">
                    <label className="flex items-center gap-2 font-body text-sm w-72">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleCustomCriterion(c.key, c.default_value)}
                      />
                      {c.label.replace(/[\d.,]+/g, "").trim() || c.key}
                    </label>
                    {checked && typeof c.default_value !== "boolean" && (
                      <input
                        type="number"
                        value={customSelection[c.key]}
                        onChange={(e) => updateCustomValue(c.key, e.target.value)}
                        className="font-mono text-sm px-2 py-1 border border-line rounded-sm bg-white w-28"
                      />
                    )}
                  </div>
                );
              })}
            </div>
            <p className="font-body text-xs text-ink-soft mt-2">
              New criteria added to the backend show up here automatically —
              nothing to update on this page when the criteria list grows.
            </p>
          </div>
        )}

        <div className="flex items-center gap-4 mb-4 flex-wrap">
          <label className="flex flex-col gap-1">
            <span className="font-body text-xs text-ink-soft">Universe to scan</span>
            <select
              value={universe}
              onChange={(e) => setUniverse(e.target.value)}
              className="font-body text-sm px-3 py-2 border border-line rounded-sm bg-white"
            >
              {universes.map((u) => (
                <option key={u.key} value={u.key}>{u.label} ({u.count} tickers)</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-body text-xs text-ink-soft">Min criteria passed (optional)</span>
            <input
              type="number"
              value={minPassed}
              onChange={(e) => setMinPassed(e.target.value)}
              placeholder="e.g. 4"
              className="font-mono text-sm px-2 py-1 border border-line rounded-sm bg-white w-24"
            />
          </label>
        </div>

        {mode === "high" && (
          <p className="font-body text-xs text-caution mb-3">
            Uses delayed data (not a real-time feed) — fine for practice and
            pattern recognition, not a substitute for a live data source
            when actually executing trades.
          </p>
        )}

        <button
          onClick={runScan}
          disabled={scanStatus?.status === "running"}
          className="font-body text-sm px-4 py-2 bg-pine text-paper rounded-sm hover:bg-pine-dim disabled:opacity-50"
        >
          {scanStatus?.status === "running" ? "Scanning…" : "Scan"}
        </button>
      </Card>

      {error && <p className="font-body text-sm text-loss mb-4">{error}</p>}

      {scanStatus && (
        <Card eyebrow={scanStatus.status === "done" ? "Complete" : "In progress"} title="Scan results" className="mb-6">
          <div className="mb-3">
            <div className="h-2 bg-line/50 rounded-sm overflow-hidden">
              <div className="h-full bg-pine transition-all" style={{ width: `${progressPct}%` }} />
            </div>
            <p className="font-body text-xs text-ink-soft mt-1">
              Scanned {scanStatus.scanned} / {scanStatus.total} — {scanStatus.matches_so_far} match{scanStatus.matches_so_far === 1 ? "" : "es"} so far
            </p>
          </div>

          {scanStatus.status === "done" && scanStatus.results && (
            <div className="flex flex-col gap-3">
              {scanStatus.results.length === 0 ? (
                <p className="font-body text-sm text-ink-soft">No tickers matched these criteria.</p>
              ) : (
                scanStatus.results.map((r) => (
                  <div key={r.ticker} className="border-l-2 border-line pl-3">
                    <div className="flex items-baseline gap-2">
                      <span className="font-mono text-sm text-ink">{r.ticker}</span>
                      <span className="font-body text-xs text-ink-soft">
                        {r.passed_count}/{r.total_count} criteria met
                      </span>
                    </div>
                    <ul className="mt-1">
                      {r.criteria.map((c) => (
                        <li key={c.key} className="font-body text-xs flex items-center gap-2">
                          <span className={c.passed === null ? "text-ink-soft" : c.passed ? "text-gain" : "text-loss"}>
                            {c.passed === null ? "—" : c.passed ? "✓" : "✗"}
                          </span>
                          <span className="text-ink-soft">{c.label}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))
              )}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
