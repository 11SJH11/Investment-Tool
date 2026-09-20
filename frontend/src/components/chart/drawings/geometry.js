// Bars and times are sorted together once, not scanned on every pointer move.
export function nearestOHLC({point,logical,bars,toX,toY,x,y,mode}) {
  if(!point||mode==='off'||!bars.length||logical==null||!Number.isFinite(logical))return point;
  const index=Math.max(0,Math.min(bars.length-1,Math.round(logical))),bar=bars[index],px=toX(index);
  if(px==null||(mode==='weak'&&Math.abs(px-x)>14))return point;
  const levels=['open','high','low','close'].map(field=>({field,price:Number(bar[field]),y:toY(Number(bar[field]))})).filter(v=>v.y!=null&&Number.isFinite(v.price));
  levels.sort((a,b)=>Math.abs(a.y-y)-Math.abs(b.y-y));
  if(!levels.length||(mode==='weak'&&Math.abs(levels[0].y-y)>14))return point;
  return {time:Math.floor(Date.parse(bar.timestamp)/1000),price:levels[0].price,snapped:levels[0].field};
}
export function translatePoints(points,origin,point) {
  return points.map(p=>({...p,time:Number(p.time)+point.time-origin.time,price:Number(p.price)+point.price-origin.price}));
}
export function constrainPoint(start,point,toScreen,fromScreen) {
  const a=toScreen(start),b=toScreen(point);if(!a||!b)return point;
  const dx=b.x-a.x,dy=b.y-a.y,angle=Math.round(Math.atan2(dy,dx)/(Math.PI/4))*Math.PI/4,length=Math.hypot(dx,dy);
  return fromScreen(a.x+Math.cos(angle)*length,a.y+Math.sin(angle)*length)||point;
}
