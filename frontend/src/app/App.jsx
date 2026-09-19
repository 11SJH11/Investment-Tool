import { useEffect, useState } from "react";
import TopNav from "../components/TopNav";
import {useUIPreference} from "./useUIPreference.js";
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
 const [active,setActive]=useUIPreference("navigation.active", "Dashboard"); const [selectedTicker,setSelectedTicker]=useState("AAPL"); const [prefs,setPrefs]=useState(loadPreferences);
 const [journalDirty,setJournalDirty]=useState(false);
 const [workspaceDirty,setWorkspaceDirty]=useState(false);
 const selectPage=next=>{if(active==="Backtest"&&next!==active&&workspaceDirty&&!confirm("Discard unsaved Strategy Workspace changes?"))return;if(active!=="Journal"||next==="Journal"||!journalDirty||confirm("Discard unsaved Journal changes?"))setActive(next);};
 useEffect(()=>{applyPreferences(prefs)},[]);
 const updatePrefs=(next)=>{setPrefs(next);savePreferences(next)};
 const order=(prefs.navOrder||sections).filter(x=>sections.includes(x)); const missing=sections.filter(x=>!order.includes(x)); const nav=[...order,...missing];
 const openCharts=t=>{setSelectedTicker(t);setActive("Charts")};
 const workspacePage = active === "Charts" || active === "Replay";
 return <div className="app-shell"><TopNav sections={nav} active={active} onSelect={selectPage}/><main id="workspace" className={`app-workspace ${workspacePage ? "chart-workspace" : ""}`}>

  {active==="Dashboard"&&<DashboardPage onNavigate={selectPage}/>}
  {active==="Screener"&&<ScreenerPage onOpenTicker={openCharts}/>} 
  {active==="Charts"&&<ChartsPage selectedTicker={selectedTicker} onTickerChange={setSelectedTicker}/>} 
  {active==="Replay"&&<StrategyLabPage initialTab="Replay" standaloneTab="Replay"/>}
  {active==="Journal"&&<JournalPage onDirtyChange={setJournalDirty}/>}
  {active==="Backtest"&&<StrategyLabPage initialTab="Backtest" standaloneTab="Backtest" onWorkspaceDirty={setWorkspaceDirty}/>}
  {active==="Investment Portfolio"&&<PortfolioPage onOpenTicker={openCharts}/>} 
  {active==="Settings"&&<SettingsPage preferences={prefs} onChange={updatePrefs}/>} 
 </main></div>
}
