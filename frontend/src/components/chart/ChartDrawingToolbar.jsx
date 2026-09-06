const groups = [
  [
    ["cursor", "⌖", "Crosshair / chart navigation"],
    ["select", "↖", "Select / move drawings"],
  ],
  [
    ["trend", "╱", "Trend line"],
    ["horizontal", "━", "Horizontal line"],
    ["horizontal-ray", "→", "Horizontal ray"],
    ["vertical", "┃", "Vertical line"],
    ["arrow", "↗", "Arrow"],
  ],
  [
    ["rectangle", "□", "Rectangle / zone"],
    ["brush", "✎", "Brush / freehand"],
    ["text", "T", "Text note"],
  ],
  [
    ["fib", "Fib", "Fibonacci retracement"],
    ["long-position", "L", "Long position · drag entry to stop, then click target"],
    ["short-position", "S", "Short position · drag entry to stop, then click target"],
  ],
];

export default function ChartDrawingToolbar({ tool, onToolChange, magnet = "weak", onMagnetChange, onUndo, onRedo, onDelete, canDelete = false, className = "" }) {
  return <aside className={`chart-drawing-toolbar ${className}`}>
    {groups.map((items, groupIndex) => <div key={groupIndex} className="drawing-tool-group">
      {items.map(([value, icon, label]) => <button key={value} type="button" title={label} aria-label={label} className={`drawing-tool-btn ${tool === value ? "active" : ""}`} onClick={() => onToolChange?.(value)}>{icon}</button>)}
    </div>)}
    <div className="drawing-tool-group">
      <button type="button" className={`drawing-tool-btn ${magnet !== "off" ? "active-soft" : ""}`} title={`Magnet: ${magnet}`} onClick={() => onMagnetChange?.(magnet === "off" ? "weak" : magnet === "weak" ? "strong" : "off")}>🧲</button>
      <button type="button" className="drawing-tool-btn" title="Undo" onClick={onUndo}>↶</button>
      <button type="button" className="drawing-tool-btn" title="Redo" onClick={onRedo}>↷</button>
      <button type="button" className="drawing-tool-btn danger" title="Delete selected drawing" disabled={!canDelete} onClick={onDelete}>⌫</button>
    </div>
  </aside>;
}
