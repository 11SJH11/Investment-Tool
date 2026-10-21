import {sandboxTimeline} from './researchSandbox.js';

export default function SandboxTimeline({run}){
 const events=sandboxTimeline(run);
 if(!events.length)return null;
 return <ol className="text-sm mt-2 max-h-64 overflow-auto" aria-label="Sandbox execution timeline">
  {events.map((event,index)=><li key={index}>
   <time dateTime={event.at}>{new Date(event.at).toLocaleString()}</time> / {event.phase} / {event.label} / {event.elapsed_seconds}s
   {event.reason&&` / ${event.reason}`}
  </li>)}
 </ol>;
}
