// Presentation only. Anchor locality to candle extrema, never to other overlays.
export function validCandle(bar) {
  return ['open','high','low','close'].every(k=>bar[k]!=null&&Number.isFinite(Number(bar[k]))) && Number(bar.high)>=Math.max(Number(bar.open),Number(bar.close),Number(bar.low)) && Number(bar.low)<=Math.min(Number(bar.open),Number(bar.close));
}
export function reviewPriceDomain(bars, overlays=[], range=null) {
  const from=Math.max(0,Math.floor(range?.from??0)),to=Math.min(bars.length-1,Math.ceil(range?.to??bars.length-1));
  const visible=bars.slice(from,to+1).filter(validCandle);
  if(!visible.length)return null;
  let low=Infinity,high=-Infinity;
  for(const bar of visible){low=Math.min(low,Number(bar.low));high=Math.max(high,Number(bar.high));}
  const minimum=Math.max(Math.abs((high+low)/2)*.0001,1e-8);
  const span=Math.max(high-low,minimum),budget=span*.5;
  let min=low,max=high;const samples=[];
  for(const overlay of overlays){
    const values=overlay.value!=null?[Number(overlay.value)]:overlay.points.filter(p=>p.time>=visible[0].time&&p.time<=visible.at(-1).time).map(p=>Number(p.value));
    const finite=values.filter(Number.isFinite);if(!finite.length)continue;
    for(const value of finite)if(value>=low-budget&&value<=high+budget){min=Math.min(min,value);max=Math.max(max,value);}
    samples.push({label:overlay.label,values:finite});
  }
  const padding=Math.max((max-min)*.05,minimum*.5);
  const priceRange={minValue:min-padding,maxValue:max+padding};
  const offScale=[];
  for(const {label,values} of samples){const below=values.filter(v=>v<priceRange.minValue),above=values.filter(v=>v>priceRange.maxValue);
    for(const [side,items] of [['below',below],['above',above]])if(items.length){let lo=Infinity,hi=-Infinity;for(const v of items){lo=Math.min(lo,v);hi=Math.max(hi,v);}offScale.push(`${label}: ${lo.toPrecision(7)}${hi!==lo?' to '+hi.toPrecision(7):''} (${side} visible scale)`);}
  }
  return {priceRange,offScale,candleLow:low,candleHigh:high,padding};
}
