import {useState} from 'react';
import AutonomousResearch from './AutonomousResearch.jsx';
import ResearchFoundations from './ResearchFoundations.jsx';

export default function ResearchHome(props){
 const [advanced,setAdvanced]=useState(false);
 if(props.mode==='Market Concepts')return <ResearchFoundations {...props}/>;
 return <><div className="ui-toolbar mt-5" aria-label="Research navigation">
  <button className={`mini-btn ${!advanced?'active-btn':''}`} aria-pressed={!advanced} onClick={()=>setAdvanced(false)}>Campaigns</button>
  <button className={`mini-btn ${advanced?'active-btn':''}`} aria-pressed={advanced} onClick={()=>setAdvanced(true)}>Advanced projects</button>
 </div>{advanced?<ResearchFoundations {...props}/>:<AutonomousResearch strategies={props.strategies}/>}</>;
}
