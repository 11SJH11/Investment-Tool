import {useState} from 'react';
export default function ReplayToolbar({busy=false,help=true,title,canPrevious,canNext,playing,speed,follow,expanded,previous,next,five,togglePlay,setSpeed,nextSession,toggleFollow,save,restart,objects,toggleExpanded,jump}) {
 const [stamp,setStamp]=useState('');
 return <div className="replay-toolbar">
   <strong className="replay-toolbar-title" title={title}>{title}</strong>
   <div className="replay-toolbar-controls">
     <button className="mini-btn" disabled={busy||!canPrevious} onClick={previous}>Previous</button>
     <button className="mini-btn" disabled={busy||!canNext} onClick={next}>Next bar</button>
     <button className="mini-btn" disabled={busy||!canNext} onClick={five}>+5 bars</button>
     <button className="mini-btn ledger-primary text-white" disabled={busy||!canNext} onClick={togglePlay}>{playing?'Pause':'Play'}</button>
     <select aria-label="Playback speed" className="input table-density" value={speed} onChange={e=>setSpeed(Number(e.target.value))}>{[.5,1,2,5,10].map(n=><option key={n} value={n}>{n}x</option>)}</select>
     <button className="mini-btn" aria-pressed={follow} onClick={toggleFollow}>Follow {follow?'on':'off'}</button>
     <button className="mini-btn" onClick={objects}>Objects</button>
     <button className="mini-btn" onClick={toggleExpanded}>{expanded?'Exit full screen':'Full screen'}</button>
   </div>
   <details className="replay-toolbar-more">
     <summary className="mini-btn">More</summary>
     <div className="replay-toolbar-menu">
       <div className="replay-jump"><label className="text-xs">Jump to (UTC)<input aria-label="Replay jump UTC" type="datetime-local" className="input mt-1" value={stamp} onChange={e=>setStamp(e.target.value)}/></label><button className="mini-btn" disabled={busy||!stamp} onClick={()=>jump(stamp+'Z')}>Jump</button></div>
       <div className="ui-toolbar mt-2"><button className="mini-btn" disabled={busy||!canNext} onClick={nextSession}>Next session</button><button className="mini-btn" onClick={save}>Save replay</button><button className="mini-btn" onClick={restart}>Restart clean</button></div>
       {help&&<p className="muted text-xs mt-2">Space: play/pause; arrows: step/review; Shift+Right: +5; B/S: focus Buy/Sell; L: limit ticket; C: queue close; Escape: cancel drawing / exit expansion. Jumping forward evaluates every intervening source bar.</p>}
     </div>
   </details>
 </div>;
}
