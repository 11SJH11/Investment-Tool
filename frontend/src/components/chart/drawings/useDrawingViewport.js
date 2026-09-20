import {useLayoutEffect,useState} from 'react';
import {createInvalidator} from './invalidation.js';
export function useDrawingViewport(chart,series,container) {
  const [revision,setRevision]=useState(0);
  useLayoutEffect(()=>{
    if(!chart||!series||!container)return;
    const scheduler=createInvalidator(()=>setRevision(n=>n+1));
    // Lightweight Charts calls primitive updateAllViews on data/price/time-scale
    // invalidation, including animated scale gestures. No idle polling required.
    const primitive={updateAllViews:scheduler.invalidate};
    series.attachPrimitive(primitive);
    chart.timeScale().subscribeVisibleLogicalRangeChange(scheduler.invalidate);
    const resize=new ResizeObserver(scheduler.invalidate);resize.observe(container);
    scheduler.invalidate();
    // Detach before the parent passive cleanup removes the chart. Detaching a
    // primitive after chart.remove() would enqueue a frame on a disposed canvas.
    return()=>{scheduler.dispose();resize.disconnect();chart.timeScale().unsubscribeVisibleLogicalRangeChange(scheduler.invalidate);series.detachPrimitive(primitive);};
  },[chart,series,container]);
  return revision;
}
