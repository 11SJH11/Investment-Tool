export function refreshedSelection(previous, response, key, params) {
  if (!response.ok) throw new Error((response.errors||[]).map(e=>`${e.module}: ${e.message}`).join('; ')||'Strategy refresh failed; existing strategies retained.');
  const strategies=response.strategies||[];
  const selected=strategies.find(s=>s.key===key)||strategies[0];
  const before=previous.find(s=>s.key===key);
  const defaults=selected?.defaults||{};
  const nextParams={...defaults};
  if(selected?.key===key)for(const name of Object.keys(defaults)){
    if(Object.hasOwn(params,name)&&params[name]!==before?.defaults?.[name])nextParams[name]=params[name];
  }
  return {strategies,key:selected?.key||'',params:nextParams,message:`Strategies refreshed: ${response.added} added / ${response.updated} updated / ${response.removed} removed.`};
}
export const normalBacktestTab = tab => ['Backtest','Runs','Run Viewer','Research Viewer','Strategies','Indicators'].includes(tab)?tab:'Backtest';
