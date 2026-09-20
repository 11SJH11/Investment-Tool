import {DEFAULT_FIB_LEVELS,POSITION} from "./models.js";
const clamp=(v,min,max)=>Math.max(min,Math.min(max,v));
function lineColor(item) { return item.color || "#60a5fa"; }
function rgba(hex, alpha = 0.12) {
  const color = hex || "#60a5fa";
  if (/^#[0-9a-fA-F]{6}$/.test(color)) {
    const r = parseInt(color.slice(1, 3), 16), g = parseInt(color.slice(3, 5), 16), b = parseInt(color.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }
  return color;
}
function dash(item) {
  if (item.lineStyle === "dashed") return "7 5";
  if (item.lineStyle === "dotted") return "2 4";
  return undefined;
}
export default function Drawing({ item, toScreen, width, height, selected, selectable, onMove, onPointMove }) {
  const points = (item.points || []).map(toScreen), color = lineColor(item), strokeWidth = Number(item.lineWidth || 2), strokeDasharray = dash(item);
  const common = { className:"drawing-stroke", stroke: color, strokeWidth, strokeDasharray, opacity: Number(item.opacity ?? 1), fill: "none", vectorEffect: "non-scaling-stroke", style: { pointerEvents: selectable ? "stroke" : "none", cursor: selectable ? "pointer" : "default" }, onPointerDown: onMove };
  const allowHandles = selected && selectable && item.type !== "brush" && !item.locked;
  const handles = allowHandles ? points.map((p, index) => p && <circle key={index} cx={p.x} cy={p.y} r="5" fill="#fff" stroke={color} strokeWidth="2" style={{ pointerEvents: "all", cursor: "grab" }} onPointerDown={(e) => onPointMove(e, index)} />) : null;

  if (item.type === "horizontal" || item.type === "horizontal-ray") {
    const p = points[0]; if (!p) return null; const x1 = item.type === "horizontal-ray" ? clamp(p.x, 0, width) : 0, label = Number(item.points[0]?.price);
    return <g><line x1={x1} y1={p.y} x2={width} y2={p.y} {...common}/><PriceTag x={width} y={p.y} price={label} color={color}/>{handles}</g>;
  }
  if (item.type === "vertical") { const p = points[0]; if (!p) return null; return <g><line x1={p.x} y1="0" x2={p.x} y2={height} {...common}/>{handles}</g>; }
  if (item.type === "trend" || item.type === "arrow") {
    const [a,b]=points; if(!a||!b)return draftHint(item, points, color);
    return <g><line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="transparent" strokeWidth="14" style={{pointerEvents:selectable?"stroke":"none",cursor:"grab"}} onPointerDown={onMove}/><line x1={a.x} y1={a.y} x2={b.x} y2={b.y} {...common} markerEnd={item.type === "arrow" ? "url(#ledger-arrow)" : undefined}/>{handles}</g>;
  }
  if (item.type === "rectangle") {
    const [a,b]=points; if(!a||!b)return draftHint(item, points, color);
    const ax=clamp(a.x,0,width), bx=clamp(b.x,0,width), rawX=Math.min(ax,bx), y=Math.min(a.y,b.y), rawW=Math.abs(bx-ax), h=Math.abs(b.y-a.y);
    // A rectangle drawn on 1m can span only a fraction of one 1h candle. Keep
    // the true timestamp anchors, but enforce a tiny render-only minimum width
    // so the object remains visible/selectable instead of appearing to vanish.
    const hasTimeSpan = Number(item.points?.[0]?.time) !== Number(item.points?.[1]?.time);
    const w = hasTimeSpan && rawW > 0 && rawW < 2 ? 2 : rawW;
    const x = Math.min(Math.max(0, rawX - Math.max(0, w - rawW) / 2), Math.max(0, width - w));
    return <g><rect x={x} y={y} width={w} height={h} stroke={color} strokeWidth={strokeWidth} strokeDasharray={strokeDasharray} fill={rgba(item.fillColor || color, Number(item.fillOpacity ?? .12))} opacity={Number(item.opacity ?? 1)} vectorEffect="non-scaling-stroke" style={{pointerEvents:selectable?"all":"none",cursor:selectable?"pointer":"default"}} onPointerDown={onMove}/>{handles}</g>;
  }
  if (item.type === "brush") {
    const clean=points.filter(Boolean); if(clean.length<2)return draftHint(item, points, color);
    return <g><polyline points={clean.map(p=>`${p.x},${p.y}`).join(" ")} strokeLinecap="round" strokeLinejoin="round" {...common}/></g>;
  }
  if (item.type === "text") {
    const p=points[0]; if(!p)return null; const fontSize=Number(item.fontSize||12), bg=item.backgroundColor||"#111827";
    return <g style={{pointerEvents:selectable?"all":"none",cursor:selectable?"pointer":"default"}} onPointerDown={onMove}><rect x={p.x-4} y={p.y-fontSize-7} width={Math.max(46,(item.text||"").length*(fontSize*.6)+8)} height={fontSize+10} rx="4" fill={rgba(bg,Number(item.backgroundOpacity??.82))}/><text x={p.x} y={p.y-4} fill={color} fontSize={fontSize} fontWeight="600">{item.text}</text>{handles}</g>;
  }
  if (item.type === "fib") {
    const [a,b]=points; if(!a||!b)return draftHint(item, points, color);
    const priceA=Number(item.points[0].price), priceB=Number(item.points[1].price), ax=clamp(a.x,0,width), bx=clamp(b.x,0,width);
    let x1=Math.min(ax,bx), x2=Math.max(ax,bx);
    if (Number(item.points?.[0]?.time) !== Number(item.points?.[1]?.time) && x2 - x1 > 0 && x2 - x1 < 2) {
      const mid=(x1+x2)/2; x1=Math.max(0,mid-1); x2=Math.min(width,mid+1);
    }
    const levels=(item.fibLevels||DEFAULT_FIB_LEVELS).filter((level)=>level.visible!==false);
    return <g onPointerDown={onMove} style={{pointerEvents:selectable?"all":"none",cursor:selectable?"pointer":"default"}}>
      {Number(item.fibFillOpacity||0)>0 && <rect x={x1} y={Math.min(a.y,b.y)} width={Math.max(1,x2-x1)} height={Math.abs(b.y-a.y)} fill={rgba(item.fibFillColor||color,Number(item.fibFillOpacity||0))}/>} 
      {levels.map(level=>{const value=Number(level.value), price=priceA+(priceB-priceA)*value, y=a.y+(b.y-a.y)*value, levelColor=level.color||color; return <g key={`${value}-${levelColor}`}><line x1={x1} y1={y} x2={x2} y2={y} stroke={levelColor} strokeWidth={Number(level.lineWidth||1)} strokeDasharray={dash(level)} opacity={value===0||value===1?1:.85}/><text x={Math.min(width-82,x2+5)} y={y+4} fill={levelColor} fontSize="10">{value}{item.showFibPrices===false?"":` · ${price.toFixed(2)}`}</text></g>})}{handles}
    </g>;
  }
  if (POSITION.has(item.type)) {
    const entry=points[0], stop=points[1], target=points[2], end=points[3]; if(!entry||!stop||!target)return null;
    const startX=clamp(entry.x,0,width);
    // Position tools are intentionally right-extending. Old malformed saved width
    // anchors (or an accidental drag to the left) are repaired visually instead of
    // painting a giant box all the way to the left edge of the chart.
    const candidateEnd = Number(end?.x);
    const endX = Number.isFinite(candidateEnd) && candidateEnd > startX + 12 ? clamp(candidateEnd, 0, width) : clamp(startX + 140, 0, width);
    const x1=startX, x2=Math.max(startX+24,endX), boxWidth=Math.max(24,x2-x1);
    const entryPrice=Number(item.points[0].price), stopPrice=Number(item.points[1].price), targetPrice=Number(item.points[2].price), risk=Math.abs(entryPrice-stopPrice), rr=risk?Math.abs(targetPrice-entryPrice)/risk:null;
    const profitColor=item.profitColor||"#22c55e", lossColor=item.lossColor||"#ef4444", opacity=Number(item.fillOpacity??.16);
    return <g onPointerDown={onMove} style={{pointerEvents:selectable?"all":"none",cursor:selectable?"pointer":"default"}}>
      <rect x={x1} y={Math.min(entry.y,target.y)} width={boxWidth} height={Math.abs(target.y-entry.y)} fill={rgba(profitColor,opacity)}/>
      <rect x={x1} y={Math.min(entry.y,stop.y)} width={boxWidth} height={Math.abs(stop.y-entry.y)} fill={rgba(lossColor,opacity)}/>
      <line x1={x1} y1={entry.y} x2={x1+boxWidth} y2={entry.y} stroke={item.entryColor||"#e5e7eb"} strokeWidth="1.5"/>
      <line x1={x1} y1={stop.y} x2={x1+boxWidth} y2={stop.y} stroke={lossColor} strokeWidth="1.5"/><line x1={x1} y1={target.y} x2={x1+boxWidth} y2={target.y} stroke={profitColor} strokeWidth="1.5"/>
      <text x={x1+6} y={entry.y-6} fill={item.entryColor||"#e5e7eb"} fontSize="10">{item.type === "long-position" ? "LONG" : "SHORT"} · R:R {rr?rr.toFixed(2):"—"}</text>{handles}
    </g>;
  }
  return null;
}
function PriceTag({ x, y, price, color }) {
  if (!Number.isFinite(price)) return null; const text=price.toFixed(Math.abs(price)>=1000?2:4), w=Math.max(54,text.length*7+10), left=Math.max(0,x-w);
  return <g style={{pointerEvents:"none"}}><rect x={left} y={y-9} width={w} height="18" rx="3" fill={color}/><text x={left+5} y={y+4} fill="#fff" fontSize="10" fontWeight="700">{text}</text></g>;
}
function draftHint(item, points, color, text = "Drag to size") {
  if (item.id !== "__draft__") return null; const p = points.find(Boolean); if (!p) return null;
  return <g><circle cx={p.x} cy={p.y} r="4.5" fill={color}/><text x={p.x+7} y={p.y-7} fill={color} fontSize="10">{text}</text></g>;
}
