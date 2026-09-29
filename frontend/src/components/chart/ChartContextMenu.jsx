import {useEffect} from 'react';

export default function ChartContextMenu({menu,onClose,onReset,onClear,canClear=false}) {
  useEffect(()=>{
    if(!menu)return undefined;
    const close=()=>onClose?.();
    const key=e=>{if(e.key==='Escape')close();};
    globalThis.addEventListener('pointerdown',close);
    globalThis.addEventListener('keydown',key);
    return()=>{globalThis.removeEventListener('pointerdown',close);globalThis.removeEventListener('keydown',key);};
  },[menu,onClose]);
  if(!menu)return null;
  return <div className="chart-context-menu" style={{left:`clamp(8px, ${menu.x}px, calc(100% - 188px))`,top:`clamp(8px, ${menu.y}px, calc(100% - 104px))`}} onPointerDown={e=>e.stopPropagation()} onContextMenu={e=>e.preventDefault()} role="menu" aria-label="Chart actions">
    <button role="menuitem" onClick={()=>{onReset?.();onClose?.();}}>Reset chart view</button>
    {canClear&&<button role="menuitem" className="danger" onClick={()=>{if(globalThis.confirm?.('Clear all drawings from this chart?'))onClear?.();onClose?.();}}>Clear all drawings</button>}
  </div>;
}
