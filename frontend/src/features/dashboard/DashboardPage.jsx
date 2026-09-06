import { useEffect, useState } from "react";
const DEFAULT = [
  {id:"replay",text:"Finish TradingView-style Replay drawings / panes / workspace polish",done:false},
  {id:"futures",text:"Add futures provider support (NQ / MNQ / continuous contracts)",done:false},
  {id:"strategy",text:"Define and code First Pullback v1, then AMN",done:false},
  {id:"broker",text:"Add read-only broker sync / automatic journal imports later",done:false},
  {id:"news",text:"Markets/news/FT integration after core trading workflow",done:false},
];
export default function DashboardPage(){
 const [items,setItems]=useState(()=>{try{return JSON.parse(localStorage.getItem("ledger.todo")||"null")||DEFAULT}catch{return DEFAULT}}); const [text,setText]=useState("");
 useEffect(()=>localStorage.setItem("ledger.todo",JSON.stringify(items)),[items]);
 const toggle=id=>setItems(xs=>xs.map(x=>x.id===id?{...x,done:!x.done}:x)); const remove=id=>setItems(xs=>xs.filter(x=>x.id!==id)); const add=()=>{if(!text.trim())return;setItems(xs=>[...xs,{id:crypto.randomUUID?.()||String(Date.now()),text:text.trim(),done:false}]);setText("")};
 return <div className="max-w-5xl"><p className="text-xs uppercase tracking-widest text-stone-500">Ledger workspace</p><h2 className="mt-1 text-3xl font-semibold">Dashboard</h2><p className="mt-2 max-w-3xl text-sm text-stone-600">For now this is your build/learning dashboard. Once Ledger is stable we can replace it with a polished overview of portfolio, journal, replay and strategy performance.</p>
 <section className="mt-6 grid gap-4 md:grid-cols-3"><Card title="Analyse"><p>Charts and Screener help you inspect markets without mixing that work into your journal.</p></Card><Card title="Practise"><p>Replay hides future candles, records practice trades and feeds them into Journal.</p></Card><Card title="Validate"><p>Backtest uses coded strategies, holdout validation and saved runs to reduce overfitting.</p></Card></section>
 <section className="mt-6 rounded-xl border border-stone-200 bg-white p-5 shadow-sm"><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="text-lg font-semibold">Ledger TODO</h3><p className="mt-1 text-xs text-stone-500">Local checklist for current kinks and planned improvements.</p></div><span className="text-xs text-stone-500">{items.filter(x=>x.done).length}/{items.length} complete</span></div><div className="mt-4 space-y-2">{items.map(item=><div key={item.id} className="flex items-center gap-3 rounded-lg border border-stone-200 px-3 py-3"><input type="checkbox" checked={item.done} onChange={()=>toggle(item.id)}/><span className={`flex-1 text-sm ${item.done?"text-stone-400 line-through":""}`}>{item.text}</span><button onClick={()=>remove(item.id)} className="text-xs text-stone-400 hover:text-red-600">Delete</button></div>)}</div><div className="mt-4 flex gap-2"><input className="input" value={text} onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==="Enter")add()}} placeholder="Add something to fix / improve…"/><button onClick={add} className="ledger-primary rounded-md px-4 py-2 text-sm text-white">Add</button></div></section>
 </div>}
function Card({title,children}){return <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm"><h3 className="font-semibold">{title}</h3><div className="mt-2 text-sm text-stone-600">{children}</div></div>}
