import { DEFAULT_FIB_LEVELS } from "./DrawingOverlay";

const labels = {
  trend: "Trend line", horizontal: "Horizontal line", "horizontal-ray": "Horizontal ray", vertical: "Vertical line",
  rectangle: "Rectangle", arrow: "Arrow", brush: "Brush", text: "Text", fib: "Fib retracement",
  "long-position": "Long position", "short-position": "Short position",
};
const hasLineStyle = new Set(["trend","horizontal","horizontal-ray","vertical","arrow","rectangle"]);

export default function DrawingObjectPanel({ drawings = [], selectedId, onSelect, onToggleVisible, onToggleLock, onDelete, onPatch, onClose }) {
  const selected = drawings.find((item) => item.id === selectedId);
  const patch = (value) => selected && onPatch?.(selected.id, value);
  return <aside className="chart-object-panel">
    <div className="chart-object-header"><div><p className="eyebrow">Chart objects</p><h4>Drawings</h4></div><button className="chart-icon-btn" onClick={onClose}>×</button></div>
    {!drawings.length ? <p className="chart-object-empty">No drawings on this symbol yet.</p> : <div className="chart-object-list">{drawings.map((item) => <div key={item.id} className={`chart-object-row ${selectedId === item.id ? "selected" : ""}`} onClick={() => onSelect?.(item.id)}>
      <button type="button" className="chart-object-eye" title={item.visible === false ? "Show" : "Hide"} onClick={(e) => { e.stopPropagation(); onToggleVisible?.(item.id); }}>{item.visible === false ? "○" : "●"}</button>
      <div className="chart-object-name"><strong>{item.text || labels[item.type] || item.type}</strong><span>{item.type}</span></div>
      <button type="button" className="chart-object-action" title={item.locked ? "Unlock" : "Lock"} onClick={(e) => { e.stopPropagation(); onToggleLock?.(item.id); }}>{item.locked ? "🔒" : "🔓"}</button>
      <button type="button" className="chart-object-action danger" title="Delete" onClick={(e) => { e.stopPropagation(); onDelete?.(item.id); }}>×</button>
    </div>)}</div>}
    {selected && <div className="drawing-style-editor">
      <div className="drawing-style-head"><strong>{selected.text || labels[selected.type] || selected.type}</strong><span>{selected.type === "brush" ? "Stroke object" : selected.locked ? "Locked" : "Editable"}</span></div>

      {selected.type !== "long-position" && selected.type !== "short-position" && <div className="drawing-style-grid">
        <label><span>Colour</span><input type="color" value={selected.color || "#60a5fa"} onChange={(e) => patch({ color:e.target.value })}/></label>
        <label><span>Width</span><select className="chart-select" value={selected.lineWidth || 2} onChange={(e) => patch({ lineWidth:Number(e.target.value) })}><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="4">4</option><option value="5">5</option></select></label>
        {hasLineStyle.has(selected.type) && <label><span>Line</span><select className="chart-select" value={selected.lineStyle || "solid"} onChange={(e)=>patch({lineStyle:e.target.value})}><option value="solid">Solid</option><option value="dashed">Dashed</option><option value="dotted">Dotted</option></select></label>}
        <label><span>Opacity</span><input className="input" type="number" min="0.1" max="1" step="0.1" value={selected.opacity ?? 1} onChange={(e)=>patch({opacity:Number(e.target.value)})}/></label>
      </div>}

      {selected.type === "rectangle" && <div className="drawing-style-grid">
        <label><span>Fill</span><input type="color" value={selected.fillColor || selected.color || "#60a5fa"} onChange={(e)=>patch({fillColor:e.target.value})}/></label>
        <label><span>Fill opacity</span><input className="input" type="number" min="0" max="1" step="0.05" value={selected.fillOpacity ?? .12} onChange={(e)=>patch({fillOpacity:Number(e.target.value)})}/></label>
      </div>}

      {selected.type === "text" && <>
        <label className="drawing-text-edit"><span>Text</span><input className="input" value={selected.text || ""} onChange={(e) => patch({ text:e.target.value })}/></label>
        <div className="drawing-style-grid"><label><span>Font size</span><input className="input" type="number" min="8" max="36" value={selected.fontSize || 12} onChange={(e)=>patch({fontSize:Number(e.target.value)})}/></label><label><span>Background</span><input type="color" value={selected.backgroundColor||"#111827"} onChange={(e)=>patch({backgroundColor:e.target.value})}/></label><label><span>BG opacity</span><input className="input" type="number" min="0" max="1" step="0.05" value={selected.backgroundOpacity??.82} onChange={(e)=>patch({backgroundOpacity:Number(e.target.value)})}/></label></div>
      </>}

      {selected.type === "fib" && <FibEditor item={selected} onPatch={patch}/>} 
      {(selected.type === "long-position" || selected.type === "short-position") && <PositionEditor item={selected} onPatch={patch}/>} 

      {selected.type === "brush" ? <p className="drawing-style-hint">Freehand strokes are intentionally not resized point-by-point. Select the stroke to copy/paste or delete it.</p> : <p className="drawing-style-hint">Crosshair mode is also selection mode: click a drawing to move it or drag its handles to resize.</p>}
    </div>}
  </aside>;
}

function FibEditor({item,onPatch}) {
  const levels=(item.fibLevels||DEFAULT_FIB_LEVELS).map((x)=>({...x,color:x.color||item.color||"#60a5fa"}));
  const update=(index,patch)=>onPatch({fibLevels:levels.map((level,i)=>i===index?{...level,...patch}:level)});
  return <div className="fib-settings">
    <div className="drawing-style-grid"><label><span>Background</span><input type="color" value={item.fibFillColor||item.color||"#60a5fa"} onChange={(e)=>onPatch({fibFillColor:e.target.value})}/></label><label><span>BG opacity</span><input className="input" type="number" min="0" max="0.5" step="0.01" value={item.fibFillOpacity??.04} onChange={(e)=>onPatch({fibFillOpacity:Number(e.target.value)})}/></label><label><span>Show prices</span><input type="checkbox" checked={item.showFibPrices!==false} onChange={(e)=>onPatch({showFibPrices:e.target.checked})}/></label></div>
    <div className="fib-level-list">{levels.map((level,index)=><div className="fib-level-row" key={`${level.value}-${index}`}><input type="checkbox" checked={level.visible!==false} onChange={(e)=>update(index,{visible:e.target.checked})}/><input className="input" type="number" step="0.001" value={level.value} onChange={(e)=>update(index,{value:Number(e.target.value)})}/><input type="color" value={level.color} onChange={(e)=>update(index,{color:e.target.value})}/></div>)}</div>
  </div>;
}
function PositionEditor({item,onPatch}) {
  return <div className="drawing-style-grid">
    <label><span>Profit</span><input type="color" value={item.profitColor||"#22c55e"} onChange={(e)=>onPatch({profitColor:e.target.value})}/></label>
    <label><span>Loss</span><input type="color" value={item.lossColor||"#ef4444"} onChange={(e)=>onPatch({lossColor:e.target.value})}/></label>
    <label><span>Entry line</span><input type="color" value={item.entryColor||"#e5e7eb"} onChange={(e)=>onPatch({entryColor:e.target.value})}/></label>
    <label><span>Fill opacity</span><input className="input" type="number" min="0" max="0.6" step="0.02" value={item.fillOpacity??.16} onChange={(e)=>onPatch({fillOpacity:Number(e.target.value)})}/></label>
  </div>;
}
