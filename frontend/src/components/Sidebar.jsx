export default function Sidebar({ sections, active, onSelect, compact = false }) {
  return <aside className={`ledger-sidebar h-screen shrink-0 overflow-y-auto border-r border-stone-200 bg-white ${compact?"w-44 p-4":"w-60 p-5"}`}>
    <div className="mb-7"><h1 className="text-2xl font-semibold">Ledger</h1><p className="mt-1 text-xs text-stone-400">Analyse · Practise · Validate</p></div>
    <nav className="space-y-1">{sections.map(section=><button key={section} onClick={()=>onSelect(section)} className={`block w-full rounded-lg px-3 py-2.5 text-left text-sm transition ${active===section?"ledger-primary text-white":"text-stone-600 hover:bg-stone-100 hover:text-stone-900"}`}>{section}</button>)}</nav>
  </aside>
}
