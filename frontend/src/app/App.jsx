import {WorkflowContext} from "./WorkflowContext.js";
import {workflowContext} from "./workflow.js";
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
 const [context,setContext]=useState(null);
 const [workspaceDirty,setWorkspaceDirty]=useState(false);
 const selectPage=next=>{if(active==="Backtest"&&workspaceDirty&&!confirm("Discard unsaved Strategy Workspace changes?"))return false;if(active==="Journal"&&journalDirty&&!confirm("Discard unsaved Journal changes?"))return false;setActive(next);setContext(null);return true;};
 const openWorkflow=(target,input)=>{const route=target==="Research"?"Charts":target;if(!selectPage(route))return;const next={...workflowContext(target,input),id:Date.now()+Math.random()};setContext(next);if(next.symbol)setSelectedTicker(next.symbol);};

 useEffect(()=>{applyPreferences(prefs)},[]);
 const updatePrefs=(next)=>{setPrefs(next);savePreferences(next)};
 const order=(prefs.navOrder||sections).filter(x=>sections.includes(x)); const missing=sections.filter(x=>!order.includes(x)); const nav=[...order,...missing];
 const openCharts=t=>openWorkflow("Charts",{symbol:t});
 const workspacePage = active === "Charts" || active === "Replay";
 return <WorkflowContext.Provider value={{open:openWorkflow,context}}><div className="app-shell"><TopNav sections={nav} active={active} onSelect={selectPage}/><main id="workspace" className={`app-workspace ${workspacePage ? "chart-workspace" : ""}`}>

  {active==="Dashboard"&&<DashboardPage onNavigate={selectPage}/>}
  {active==="Screener"&&<ScreenerPage onOpenTicker={openCharts} onWorkflow={openWorkflow}/>}
  {active==="Charts"&&<ChartsPage key={context?.target==="Charts"||context?.target==="Research"?context.id:"charts"} selectedTicker={selectedTicker} onTickerChange={setSelectedTicker}/>}
  {active==="Replay"&&<StrategyLabPage initialTab="Replay" standaloneTab="Replay"/>}
  {active==="Journal"&&<JournalPage onDirtyChange={setJournalDirty}/>}
  {active==="Backtest"&&<StrategyLabPage initialTab="Backtest" standaloneTab="Backtest" onWorkspaceDirty={setWorkspaceDirty}/>}
  {active==="Investment Portfolio"&&<PortfolioPage onOpenTicker={openCharts} onWorkflow={openWorkflow}/>}
  {active==="Settings"&&<SettingsPage preferences={prefs} onChange={updatePrefs}/>}
 </main></div></WorkflowContext.Provider>
}
