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

function lowerBound(values,target) {
  let lo=0,hi=values.length;
  while(lo<hi){const mid=(lo+hi)>>1;if(values[mid]<target)lo=mid+1;else hi=mid;}
  return lo;
}

/**
 * Project an absolute market timestamp onto the current chart's bar lattice.
 *
 * Lightweight Charts compresses market closures into a single logical gap. A
 * wall-clock interpolation through a 17-hour/weekend closure therefore moves a
 * drawing dramatically when the chart changes timeframe. We interpolate
 * normally inside a session, but treat large gaps as discontinuities and keep
 * anchors close to the appropriate session edge.
 */
export function marketTimeToLogical(times,target,step=60) {
  if(!times?.length||!Number.isFinite(Number(target)))return null;
  const value=Number(target),typical=Math.max(1,Number(step)||60),index=lowerBound(times,value);
  if(index<times.length&&times[index]===value)return index;
  if(index<=0)return Math.max(-24,(value-times[0])/typical);
  if(index>=times.length)return (times.length-1)+Math.min(24,(value-times.at(-1))/typical);
  const leftIndex=index-1,left=times[leftIndex],right=times[index],gap=right-left;
  if(gap<=typical*2.5)return leftIndex+(value-left)/Math.max(1,gap);

  const fromLeft=(value-left)/typical,toRight=(right-value)/typical;
  if(fromLeft<=1)return leftIndex+Math.min(.95,Math.max(0,fromLeft));
  if(toRight<=1)return index-Math.min(.95,Math.max(0,toRight));
  return (value-left)<=(right-value)?leftIndex+.95:index-.95;
}

/** Inverse of marketTimeToLogical for pointer gestures on a compressed chart. */
export function logicalToMarketTime(times,logical,step=60,{clamp=false}={}) {
  if(!times?.length||!Number.isFinite(Number(logical)))return null;
  const value=Number(logical),typical=Math.max(1,Number(step)||60),last=times.length-1;
  if(clamp){if(value<=0)return times[0];if(value>=last)return times[last];}
  if(value<=0)return Math.round(times[0]+value*typical);
  if(value>=last)return Math.round(times[last]+(value-last)*typical);
  const left=Math.floor(value),right=Math.ceil(value),fraction=value-left;
  if(left===right)return times[left];
  const gap=times[right]-times[left];
  if(gap<=typical*2.5)return Math.round(times[left]+gap*fraction);
  // There is no tradable wall-clock time represented by the middle of an
  // overnight/weekend logical gap. Stay within one normal bar of either edge.
  if(fraction<=.5)return Math.round(times[left]+typical*(fraction/.5));
  return Math.round(times[right]-typical*((1-fraction)/.5));
}

/**
 * Convert a possibly-fractional logical index to a pixel x coordinate.
 *
 * Lightweight Charts only accepts integer logical indexes in its internal
 * indexToCoordinate path; passing a fractional logical can resolve to x=0.
 * Cross-timeframe drawings routinely have anchors between the current
 * timeframe's bars, so resolve the surrounding integer bar coordinates and
 * interpolate between them instead of passing the fractional index through.
 */
export function logicalToCoordinateInterpolated(logical,toCoordinate) {
  const value=Number(logical);
  if(!Number.isFinite(value)||typeof toCoordinate!=='function')return null;
  const left=Math.floor(value),right=Math.ceil(value);
  const leftCoordinate=toCoordinate(left);
  if(leftCoordinate==null||!Number.isFinite(Number(leftCoordinate)))return null;
  const xLeft=Number(leftCoordinate);
  if(left===right)return xLeft;
  const rightCoordinate=toCoordinate(right);
  if(rightCoordinate==null||!Number.isFinite(Number(rightCoordinate)))return null;
  const xRight=Number(rightCoordinate);
  return xLeft+(value-left)*(xRight-xLeft);
}

export function translatePoints(points,origin,point) {
  return points.map(p=>({...p,time:Number(p.time)+point.time-origin.time,price:Number(p.price)+point.price-origin.price}));
}

/** Translate a whole drawing by visual/logical bars instead of wall-clock time. */
export function translatePointsLogical(points,originLogicals,deltaLogical,priceDelta,toTime) {
  return points.map((p,index)=>{
    const base=Number(originLogicals?.[index]);
    const time=Number.isFinite(base)?toTime(base+deltaLogical):Number(p.time);
    return {...p,time:Number.isFinite(Number(time))?Number(time):Number(p.time),price:Number(p.price)+priceDelta};
  });
}

export function constrainPoint(start,point,toScreen,fromScreen) {
  const a=toScreen(start),b=toScreen(point);if(!a||!b)return point;
  const dx=b.x-a.x,dy=b.y-a.y,angle=Math.round(Math.atan2(dy,dx)/(Math.PI/4))*Math.PI/4,length=Math.hypot(dx,dy);
  return fromScreen(a.x+Math.cos(angle)*length,a.y+Math.sin(angle)*length)||point;
}
