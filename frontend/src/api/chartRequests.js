export function stableKey(value) {
  if(Array.isArray(value))return '['+value.map(stableKey).join(',')+']';
  if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+stableKey(value[k])).join(',')+'}';
  return JSON.stringify(value);
}
export function createRequestCache({ttl=15000,limit=32,now=()=>Date.now()}={}) {
  const entries=new Map();
  return {clear(){entries.clear();},get(key,loader,{refresh=false}={}) {
    const old=entries.get(key);
    if(old&&(!refresh||(old.refresh&&old.pending))&&(old.pending||now()-old.at<ttl))return old.promise;
    const entry={pending:true,refresh,at:now()};
    entry.promise=Promise.resolve().then(loader).then(value=>{entry.pending=false;entry.at=now();while(entries.size>limit){const victim=[...entries].find(([k,v])=>k!==key&&!v.pending);if(!victim)break;entries.delete(victim[0]);}return value;},error=>{if(entries.get(key)===entry)entries.delete(key);throw error;});
    entries.set(key,entry);return entry.promise;
  }};
}
export const chartRequests=createRequestCache();
