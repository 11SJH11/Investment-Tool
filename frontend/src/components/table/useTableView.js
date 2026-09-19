import {useMemo} from 'react';
import {useUIPreference} from '../../app/useUIPreference.js';
import {blankView,normalizeView,tableRows,initialTableView} from './tableModel.js';
export function useTableView(id,columns,rows=[],defaults={}) {
  const [stored,setStored]=useUIPreference(`table.${id}`,initialTableView(id,columns,defaults));
  const view=normalizeView(stored,columns,defaults);
  const setView=update=>setStored(old=>typeof update==='function'?update(normalizeView(old,columns,defaults)):{...normalizeView(old,columns,defaults),...update});
  const signature=JSON.stringify(view);
  const filtered=useMemo(()=>tableRows(rows,columns,JSON.parse(signature)),[rows,columns,signature]);
  return {view,setView,filtered,reset:()=>setStored(blankView(columns,defaults))};
}
