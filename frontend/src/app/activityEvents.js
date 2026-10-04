const listeners=new Set();
export function notifyActivity(event){for(const listener of listeners)listener({...event,id:event.id||crypto.randomUUID(),created_at:new Date().toISOString()});}
export function subscribeActivity(listener){listeners.add(listener);return()=>listeners.delete(listener);}
export function jobTransitions(previous,jobs){
 return jobs.filter(job=>previous.has(job.id)&&previous.get(job.id)!==job.status&&['completed','failed','cancelled'].includes(job.status));
}
export function jobDestination(job){
 if(job.status!=='completed')return null;
 return job.payload?.experiment_group?{experimentGroup:job.payload.experiment_group}:job.run_id?{runId:job.run_id}:null;
}

const busyListeners=new Set(),pending=new Map();
export function subscribeBusy(listener){busyListeners.add(listener);listener([...pending.values()]);return()=>busyListeners.delete(listener)}
export function beginRequest(label){const id=crypto.randomUUID();pending.set(id,label);for(const listener of busyListeners)listener([...pending.values()]);return()=>{pending.delete(id);for(const listener of busyListeners)listener([...pending.values()])}}
export function requestLabel(path,method='GET'){
 if(/\/(jobs|compute-settings|status|research-experiments)(\?|$)/.test(path)&&method==='GET')return null;
 if(path.includes('/review')||path.includes('/audit-bars'))return 'Loading trade review';
 if(path.includes('chart-data'))return 'Loading chart';
 if(path.includes('/replay'))return 'Loading Replay';
 if(path.endsWith('/sync'))return 'Synchronising broker';
 if(path.includes('/runs/'))return 'Loading saved run';
 if(method!=='GET')return path.includes('settings')?'Saving settings':'Working';
 return null;
}
