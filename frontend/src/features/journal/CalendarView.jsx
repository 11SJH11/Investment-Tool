import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import { money, rValue, sourceLabels } from "./journalUtils";

function monthValue() { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0,7); }

export default function CalendarView() {
  const [month, setMonth] = useState(monthValue());
  const [source, setSource] = useState("");
  const [days, setDays] = useState([]);
  const [error, setError] = useState("");
  useEffect(() => { api.journalCalendar(month, source).then((r) => setDays(r.days || [])).catch((e) => setError(e.message)); }, [month, source]);
  const map = useMemo(() => Object.fromEntries(days.map((d) => [d.day, d])), [days]);
  const [year, mon] = month.split("-").map(Number);
  const first = new Date(year, mon - 1, 1);
  const start = new Date(year, mon - 1, 1 - first.getDay());
  const cells = Array.from({ length: 42 }, (_, i) => { const d = new Date(start); d.setDate(start.getDate() + i); return d; });

  return <>
    <div className="flex flex-wrap items-end gap-3"><label><span className="mb-1 block text-xs text-stone-500">Month</span><input type="month" className="input w-44" value={month} onChange={(e) => setMonth(e.target.value)} /></label><label><span className="mb-1 block text-xs text-stone-500">Source</span><select className="input w-52" value={source} onChange={(e) => setSource(e.target.value)}><option value="">All sources</option>{Object.entries(sourceLabels).map(([k,v]) => <option key={k} value={k}>{v}</option>)}</select></label></div>
    {error && <p className="mt-3 text-sm text-red-700">{error}</p>}
    <div className="mt-5 grid grid-cols-7 overflow-hidden rounded-xl border border-stone-200 bg-white shadow-sm">
      {["Sun","Mon","Tue","Wed","Thu","Fri","Sat"].map((d) => <div key={d} className="border-b border-stone-200 bg-stone-50 px-3 py-2 text-xs font-medium text-stone-500">{d}</div>)}
      {cells.map((date) => {
        const key = `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`;
        const day = map[key]; const inMonth = date.getMonth() === mon - 1; const pnl = Number(day?.pnl_amount || 0); const r = Number(day?.r_total || 0);
        return <div key={key} className={`min-h-28 border-b border-r border-stone-100 p-2 ${inMonth ? "" : "bg-stone-50/60 text-stone-300"}`}><div className="text-right text-xs">{date.getDate()}</div>{day && <div className={`mt-2 rounded-md p-2 text-xs ${pnl > 0 || (pnl === 0 && r > 0) ? "bg-emerald-50 text-emerald-800" : pnl < 0 || r < 0 ? "bg-red-50 text-red-800" : "bg-stone-100 text-stone-700"}`}><p className="font-semibold">{day.trades} trade{day.trades === 1 ? "" : "s"}</p><p className="mt-1">{day.wins}W · {day.losses}L · {day.breakevens} B/E</p><p className="mt-1">{rValue(day.r_total)} · {money(day.pnl_amount)}</p></div>}</div>;
      })}
    </div>
  </>;
}
