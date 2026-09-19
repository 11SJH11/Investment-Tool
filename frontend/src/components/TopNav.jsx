const labels={Dashboard:'Overview',Screener:'Research','Investment Portfolio':'Portfolio'};
export default function TopNav({sections,active,onSelect}) {
  return <header className="app-topbar"><a className="skip-link" href="#workspace">Skip to content</a><button className="app-brand" onClick={()=>onSelect('Dashboard')} aria-label="Ledger home">LEDGER</button><nav aria-label="Main navigation">{sections.map(section=><button key={section} aria-current={active===section?'page':undefined} onClick={()=>onSelect(section)}>{labels[section]||section}</button>)}</nav></header>;
}
