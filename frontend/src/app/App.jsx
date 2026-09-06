import { useEffect, useState } from "react";
import Sidebar from "../components/Sidebar";
import DashboardPage from "../features/dashboard/DashboardPage";
import ScreenerPage from "../features/screener/ScreenerPage";
import ChartsPage from "../features/charts/ChartsPage";
import PortfolioPage from "../features/portfolio/PortfolioPage";
import JournalPage from "../features/journal/JournalPage";
import StrategyLabPage from "../features/strategy-lab/StrategyLabPage";
import SettingsPage from "../features/settings/SettingsPage";
import { sections } from "./navigation";
import { applyPreferences, loadPreferences, savePreferences } from "./preferences";

export default function App(){
 const [active,setActive]=useState("Dashboard"); const [selectedTicker,setSelectedTicker]=useState("AAPL"); const [prefs,setPrefs]=useState(loadPreferences);
 useEffect(()=>{applyPreferences(prefs)},[]);
 const updatePrefs=(next)=>{setPrefs(next);savePreferences(next)};
 const order=(prefs.navOrder||sections).filter(x=>sections.includes(x)); const missing=sections.filter(x=>!order.includes(x)); const nav=[...order,...missing];
 const openCharts=t=>{setSelectedTicker(t);setActive("Charts")};
 const workspacePage = active === "Charts" || active === "Replay";
 return <div className="flex h-screen overflow-hidden bg-stone-50 text-stone-900"><Sidebar sections={nav} active={active} onSelect={setActive} compact={prefs.sidebar==="compact"}/><main className={`flex-1 overflow-y-auto ${workspacePage ? "p-3 lg:p-4" : prefs.density==="compact"?"p-5 lg:p-6":"p-8 lg:p-10"}`}>
  {active==="Dashboard"&&<DashboardPage/>}
  {active==="Screener"&&<ScreenerPage onOpenTicker={openCharts}/>} 
  {active==="Charts"&&<ChartsPage selectedTicker={selectedTicker} onTickerChange={setSelectedTicker}/>} 
  {active==="Replay"&&<StrategyLabPage initialTab="Replay" standaloneTab="Replay"/>}
  {active==="Journal"&&<JournalPage/>}
  {active==="Backtest"&&<StrategyLabPage initialTab="Backtest" standaloneTab="Backtest"/>}
  {active==="Investment Portfolio"&&<PortfolioPage onOpenTicker={openCharts}/>} 
  {active==="Settings"&&<SettingsPage preferences={prefs} onChange={updatePrefs}/>} 
 </main></div>
}
