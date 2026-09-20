// Coalesce chart invalidations; no self-scheduling work while the chart is idle.
export function createInvalidator(redraw,request=globalThis.requestAnimationFrame,cancel=globalThis.cancelAnimationFrame) {
  let pending=null,closed=false;
  return {invalidate(){if(!closed&&pending===null)pending=request(()=>{pending=null;if(!closed)redraw();});},dispose(){closed=true;if(pending!==null)cancel(pending);pending=null;}};
}
