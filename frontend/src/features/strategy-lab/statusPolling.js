export const activeStatus = status => ['queued','preparing data','preparing shared data','running','analysing results','saving'].includes(status);
export const researchCount = job => job?.payload?.research_count ?? job?.payload?.research_children?.length ?? 0;

// One in-flight request/timer per resource, shared by all mounted subscribers.
export function createStatusPoller(fetcher, isActive, delay=1500, clock=globalThis) {
  const listeners=new Set();let data=null,inflight=null,timer=null;
  const clear=()=>{if(timer!=null)clock.clearTimeout(timer);timer=null;};
  const refresh=()=>{
    if(inflight)return inflight;
    clear();
    inflight=Promise.resolve().then(fetcher).then(next=>{data=next;for(const listener of listeners)listener(data,null);return data;},error=>{for(const listener of listeners)listener(data,error);return data;}).finally(()=>{
      inflight=null;if(listeners.size&&data&&isActive(data))timer=clock.setTimeout(refresh,delay);
    });
    return inflight;
  };
  const subscribe=listener=>{
    listeners.add(listener);if(data)listener(data,null);
    if(listeners.size===1){clock.addEventListener?.('focus',refresh);refresh();}
    return()=>{listeners.delete(listener);if(!listeners.size){clear();clock.removeEventListener?.('focus',refresh)}};
  };
  return {subscribe,refresh};
}

// Older running servers remain usable until their next normal restart.
export async function fetchResearchUpdate(api,group) {
  try{return {status:await api.researchExperimentStatus(group)};}
  catch(error){if(error.status!==404)throw error;return {detail:await api.strategyLabExperiment(group)};}
}
