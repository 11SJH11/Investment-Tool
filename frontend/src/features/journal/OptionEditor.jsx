import { useState } from 'react';
import { moveOption, splitOptions } from './journalPreferences';
export default function OptionEditor({options=[], onChange}) {
  const [paste,setPaste] = useState('');
  return <fieldset className="space-y-2"><legend className="mb-2 text-xs font-medium">Options</legend>
    {options.map((option,index)=><div key={index} className="flex gap-2">
      <input aria-label={`Option ${index+1}`} className="input min-w-0" value={option} onChange={e=>onChange(options.map((v,i)=>i===index?e.target.value:v))}/>
      <button type="button" className="mini-btn" aria-label={`Move option ${index+1} up`} disabled={!index} onClick={()=>onChange(moveOption(options,index,-1))}>↑</button>
      <button type="button" className="mini-btn" aria-label={`Move option ${index+1} down`} disabled={index===options.length-1} onClick={()=>onChange(moveOption(options,index,1))}>↓</button>
      <button type="button" className="mini-btn" aria-label={`Remove option ${index+1}`} onClick={()=>onChange(options.filter((_,i)=>i!==index))}>×</button>
    </div>)}
    <button type="button" className="mini-btn" onClick={()=>onChange([...options,''])}>+ Add option</button>
    <details><summary className="cursor-pointer text-xs">Paste multiple options</summary><textarea aria-label="Paste options" className="input mt-2" value={paste} onChange={e=>setPaste(e.target.value)} placeholder="Separate options with newlines, commas or /"/><button type="button" className="mini-btn mt-2" onClick={()=>{onChange([...new Set([...options.filter(Boolean),...splitOptions(paste)])]);setPaste('');}}>Add pasted options</button></details>
  </fieldset>;
}
