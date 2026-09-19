export const blankView = (columns,defaults={}) => ({columns:columns.filter(c=>!c.hidden).map(c=>c.key),order:columns.map(c=>c.key),density:'compact',filters:{},search:'',sort:{key:columns[0]?.key,direction:'asc'},...defaults});
export function normalizeView(value,columns,defaults={}) {
  const base=blankView(columns,defaults),keys=new Set(columns.map(c=>c.key)),v=value&&typeof value==='object'?value:{};
  const visible=Array.isArray(v.columns)?[...new Set(v.columns.filter(k=>keys.has(k)))]:base.columns;
  return {...base,...v,columns:visible.length?visible:base.columns,order:[...new Set([...(Array.isArray(v.order)?v.order.filter(k=>keys.has(k)):[]),...base.order])],density:v.density==='comfortable'?'comfortable':'compact',filters:v.filters&&typeof v.filters==='object'?v.filters:{},sort:keys.has(v.sort?.key)?v.sort:base.sort};
}
export const cellValue=(row,column)=>column.value?column.value(row):row[column.key];
export function matches(value,rule) {
  if(rule==null||rule==='')return true;
  if(Array.isArray(rule))return !rule.length||rule.some(v=>(Array.isArray(value)?value:[value]).some(x=>String(x??'')===String(v)));
  if(typeof rule==='object') {
    const hasMin=rule.min!==''&&rule.min!=null,hasMax=rule.max!==''&&rule.max!=null;
    if(!hasMin&&!hasMax)return true;
    if(value==null||value==='')return false;
    if(rule.kind==='number') {
      const n=Number(value);if(!Number.isFinite(n))return false;
      if(rule.operator==='greater')return !hasMin||n>Number(rule.min);
      if(rule.operator==='less')return !hasMax||n<Number(rule.max);
      return (!hasMin||n>=Number(rule.min))&&(!hasMax||n<=Number(rule.max));
    }
    return (!hasMin||String(value).slice(0,10)>=rule.min)&&(!hasMax||String(value).slice(0,10)<=rule.max);
  }
  return String(value??'').toLocaleLowerCase().includes(String(rule).toLocaleLowerCase());
}
export function tableRows(rows,columns,view) {
  const map=Object.fromEntries(columns.map(c=>[c.key,c]));
  return rows.filter(row=>(!view.search||columns.some(c=>String(cellValue(row,c)??'').toLocaleLowerCase().includes(view.search.toLocaleLowerCase())))&&Object.entries(view.filters||{}).every(([key,rule])=>!map[key]||matches(cellValue(row,map[key]),rule))).sort((a,b)=>{
    const c=map[view.sort?.key];if(!c)return 0;const x=cellValue(a,c),y=cellValue(b,c);
    if(x==null)return y==null?0:1;if(y==null)return -1;
    return (c.kind==='number'?Number(x)-Number(y):String(x).localeCompare(String(y)))*(view.sort.direction==='desc'?-1:1);
  });
}
export function filterLabel(rule){return Array.isArray(rule)?rule.join(', '):typeof rule==='object'?`${rule.operator==='greater'?'>':rule.operator==='less'?'<':'between'} ${rule.operator==='less'?rule.max:rule.min??''}${rule.operator==='between'||!rule.operator?` – ${rule.max??''}`:''}`:String(rule??'');}

// Read older presentation keys once; the new saved view takes precedence.
export function initialTableView(id,columns,defaults={},storage=globalThis.localStorage) {
  const base=blankView(columns,defaults);
  const read=key=>{try{return JSON.parse(storage.getItem(key));}catch{return null;}};
  const current=read(`ledger.ui.table.${id}`);
  if(current)return normalizeView(current,columns,defaults);
  if(id==='journal') {const saved=read('ledger.journal.tableColumns.v1');if(Array.isArray(saved))base.columns=saved;}
  if(id==='runs')for(const key of ['columns','filters','sort']){const saved=read(`ledger.ui.runs.${key}`);if(saved!=null)base[key]=saved;}
  return normalizeView(base,columns,defaults);
}
