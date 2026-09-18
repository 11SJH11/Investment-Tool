import {useUIPreference} from '../app/useUIPreference.js';

export function Button({primary=false, className='', ...props}) {
  return <button type="button" className={`ui-button ${primary?'ui-primary':''} ${className}`} {...props}/>;
}
export function Panel({children, className='', ...props}) { return <section className={`ui-panel ${className}`} {...props}>{children}</section>; }
export function PageToolbar({children}) { return <div className="ui-toolbar">{children}</div>; }
export function FormGrid({children}) { return <div className="ui-form-grid">{children}</div>; }
export function MetricGrid({children}) { return <dl className="ui-metric-grid">{children}</dl>; }
export function MetricCard({label, children}) { return <div className="min-w-0"><dt className="text-xs text-stone-500">{label}</dt><dd className="mt-1 break-words text-sm">{children}</dd></div>; }
export function Section({id, title, children}) {
  const [open, setOpen] = useUIPreference(`section.${id}`, false);
  return <details className="ui-section" open={open} onToggle={e=>{if(e.currentTarget.open!==open)setOpen(e.currentTarget.open);}}><summary>{title}</summary><div className="mt-4">{children}</div></details>;
}
export function TabBar({value, options, onChange, label}) {
  return <div className="ui-toolbar" role="group" aria-label={label}>{options.map(option=><Button key={option} primary={value===option} aria-pressed={value===option} onClick={()=>onChange(option)}>{option}</Button>)}</div>;
}
