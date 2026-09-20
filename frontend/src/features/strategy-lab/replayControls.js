export function replayShortcut(event,element) {
 if(event.defaultPrevented||event.ctrlKey||event.metaKey||event.altKey||event.repeat||element?.isContentEditable||['INPUT','TEXTAREA','SELECT','BUTTON'].includes(element?.tagName))return null;
 if(event.code==='Space')return 'play';
 if(event.key==='ArrowRight')return event.shiftKey?'five':'next';
 if(event.key==='ArrowLeft')return 'previous';
 return {b:'buy',s:'sell',l:'limit',c:'close',Escape:'escape'}[event.key==='Escape'?event.key:String(event.key).toLowerCase()]||null;
}
export function jumpCursor(bars,stamp,minimum=1) {
 const target=Date.parse(stamp);if(!Number.isFinite(target)||!bars.length)return null;
 if(target<Date.parse(bars[Math.max(0,minimum-1)].timestamp)||target>Date.parse(bars.at(-1).timestamp))return null;
 let lo=0,hi=bars.length;while(lo<hi){const mid=(lo+hi)>>1;if(Date.parse(bars[mid].timestamp)<=target)lo=mid+1;else hi=mid;}
 return Math.max(minimum,lo);
}
