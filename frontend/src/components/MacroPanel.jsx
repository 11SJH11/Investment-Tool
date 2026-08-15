import { useEffect, useState } from "react";
import Card from "./Card";
import { api } from "../api";

const ORDER = ["fed_funds_rate", "treasury_10y", "cpi_yoy", "unemployment_rate"];

export default function MacroPanel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.macro().then(setData).catch((e) => setError(e.message));
  }, []);

  return (
    <Card eyebrow="Background" title="Macro context">
      <p className="font-body text-xs text-ink-soft mb-3">
        Informational only — not a signal. Useful backdrop for reading valuations.
      </p>
      {error && (
        <p className="font-body text-xs text-ink-soft italic">
          {error.includes("FRED_API_KEY")
            ? "Add a free FRED API key to your backend's .env file to enable this — see .env.example."
            : `Couldn't load: ${error}`}
        </p>
      )}
      {data && (
        <div className="grid grid-cols-2 gap-x-6 gap-y-2">
          {ORDER.filter((k) => data[k] && !data[k].error).map((key) => {
            const d = data[key];
            return (
              <div key={key} className="flex justify-between items-baseline font-mono text-sm tabular-nums">
                <span className="font-body text-xs text-ink-soft">{d.label}</span>
                <span className="text-ink">
                  {d.value}{d.unit === "%" ? "%" : ""}
                  {d.trend && (
                    <span className={`ml-1 text-xs ${d.trend === "rising" ? "text-caution" : d.trend === "falling" ? "text-slate" : "text-ink-soft"}`}>
                      {d.trend === "rising" ? "↑" : d.trend === "falling" ? "↓" : "→"}
                    </span>
                  )}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
