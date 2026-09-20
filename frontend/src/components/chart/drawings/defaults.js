const KEY="ledger.drawingDefaults.v1";
export const DRAWING_TYPES=["trend","horizontal","horizontal-ray","vertical","rectangle","fib","arrow","text","brush","long-position","short-position"];
export function readDrawingDefaults(){try{return JSON.parse(localStorage.getItem(KEY)||"{}")}catch{return {}}}
export function saveDrawingDefault(type,value){const all=readDrawingDefaults();all[type]=value;localStorage.setItem(KEY,JSON.stringify(all));}
export function resetDrawingDefault(type){const all=readDrawingDefaults();delete all[type];localStorage.setItem(KEY,JSON.stringify(all));}
export function drawingStyle(type){const value=readDrawingDefaults()[type]||{};return Object.fromEntries(Object.entries(value).filter(([k])=>["color","lineWidth","lineStyle","fillColor","fillOpacity"].includes(k)));}
