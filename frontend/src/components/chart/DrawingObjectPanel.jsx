const labels = {
  trend: "Trend line", horizontal: "Horizontal line", "horizontal-ray": "Horizontal ray", vertical: "Vertical line",
  rectangle: "Rectangle", arrow: "Arrow", brush: "Brush", text: "Text", fib: "Fib retracement",
  "long-position": "Long position", "short-position": "Short position",
};

export default function DrawingObjectPanel({ drawings = [], selectedId, onSelect, onToggleVisible, onToggleLock, onDelete, onPatch, onClose }) {
  const selected = drawings.find((item) => item.id === selectedId);
  return <aside className="chart-object-panel">
    <div className="chart-object-header"><div><p className="eyebrow">Chart objects</p><h4>Drawings</h4></div><button className="chart-icon-btn" onClick={onClose}>×</button></div>
    {!drawings.length ? <p className="chart-object-empty">No drawings on this symbol yet.</p> : <div className="chart-object-list">{drawings.map((item) => <div key={item.id} className={`chart-object-row ${selectedId === item.id ? "selected" : ""}`} onClick={() => onSelect?.(item.id)}>
      <button type="button" className="chart-object-eye" title={item.visible === false ? "Show" : "Hide"} onClick={(e) => { e.stopPropagation(); onToggleVisible?.(item.id); }}>{item.visible === false ? "○" : "●"}</button>
      <div className="chart-object-name"><strong>{item.text || labels[item.type] || item.type}</strong><span>{item.type}</span></div>
      <button type="button" className="chart-object-action" title={item.locked ? "Unlock" : "Lock"} onClick={(e) => { e.stopPropagation(); onToggleLock?.(item.id); }}>{item.locked ? "🔒" : "🔓"}</button>
      <button type="button" className="chart-object-action danger" title="Delete" onClick={(e) => { e.stopPropagation(); onDelete?.(item.id); }}>×</button>
    </div>)}</div>}
    {selected && <div className="drawing-style-editor">
      <div className="drawing-style-head"><strong>{selected.text || labels[selected.type] || selected.type}</strong><span>{selected.locked ? "Locked" : "Editable"}</span></div>
      <div className="drawing-style-grid"><label><span>Colour</span><input type="color" value={selected.color || "#60a5fa"} onChange={(e) => onPatch?.(selected.id, { color:e.target.value })}/></label><label><span>Width</span><select className="chart-select" value={selected.lineWidth || 2} onChange={(e) => onPatch?.(selected.id, { lineWidth:Number(e.target.value) })}><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="4">4</option></select></label></div>
      {selected.type === "text" && <label className="drawing-text-edit"><span>Text</span><input className="input" value={selected.text || ""} onChange={(e) => onPatch?.(selected.id, { text:e.target.value })}/></label>}
      <p className="drawing-style-hint">Use the Select tool to drag the object or its anchor handles on the chart.</p>
    </div>}
  </aside>;
}
