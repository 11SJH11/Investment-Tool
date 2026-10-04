// Bounded, short-lived cache. Never recalculates a saved result.
export function createSectionCache(fetcher,limit=9,ttl=30000){
 const cache=new Map();
 return {get(id,section){const key=`${id}:${section}`,old=cache.get(key);if(old&&old.until>Date.now())return old.promise;
 const promise=Promise.resolve().then(()=>fetcher(id,section)).catch(error=>{cache.delete(key);throw error});
 cache.delete(key);cache.set(key,{promise,until:Date.now()+ttl});while(cache.size>limit)cache.delete(cache.keys().next().value);return promise;
 },clear(){cache.clear()}};
}
