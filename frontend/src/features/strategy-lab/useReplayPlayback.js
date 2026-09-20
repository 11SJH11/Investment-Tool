import {useEffect,useRef} from 'react';
import {replayShortcut} from './replayControls.js';
export function useReplayPlayback({playing,speed,ready,finished,actions}) {
 const latest=useRef(actions);latest.current=actions;
 useEffect(()=>{if(!playing||!ready||finished)return;const timer=setInterval(()=>latest.current.next(),Math.max(80,Math.round(1000/Number(speed||1))));return()=>clearInterval(timer);},[playing,speed,ready,finished]);
 useEffect(()=>{const handler=event=>{if(!ready)return;const action=replayShortcut(event,document.activeElement);if(action&&latest.current[action]){event.preventDefault();latest.current[action]();}};window.addEventListener('keydown',handler);return()=>window.removeEventListener('keydown',handler);},[ready]);
}
