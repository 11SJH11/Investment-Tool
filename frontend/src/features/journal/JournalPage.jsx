import { useState } from "react";
import CalendarView from "./CalendarView";
import DailyReviewView from "./DailyReviewView";
import PlaybookView from "./PlaybookView";
import TradesView from "./TradesView";
import AnalysisView from "./AnalysisView";

const tabs = ["Trades", "Analysis", "Calendar", "Daily Review", "Playbook"];
export default function JournalPage() {
  const [tab, setTab] = useState("Trades");
  return <div className="max-w-[1550px]"><div><p className="text-xs uppercase tracking-widest text-stone-500">Trading journal</p><h2 className="mt-1 text-3xl font-semibold">Journal</h2><p className="mt-2 max-w-4xl text-sm text-stone-600">Manual trades use your actual execution facts; Ledger derives the arithmetic. Future broker/replay/backtest imports will use the same journal model automatically.</p></div>
    <div className="mt-6 flex flex-wrap gap-1 border-b border-stone-200">{tabs.map((item) => <button key={item} onClick={() => setTab(item)} className={`border-b-2 px-4 py-2 text-sm ${tab === item ? "border-stone-900 font-medium text-stone-900" : "border-transparent text-stone-500 hover:text-stone-900"}`}>{item}</button>)}</div>
    <div className="mt-6">{tab === "Trades" && <TradesView />}{tab === "Analysis" && <AnalysisView />}{tab === "Calendar" && <CalendarView />}{tab === "Daily Review" && <DailyReviewView />}{tab === "Playbook" && <PlaybookView />}</div>
  </div>;
}
