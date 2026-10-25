export function emitDiagnostics(events, seen, logger=console){
 for(const event of events){
  if(!event?.event_id||seen.has(event.event_id))continue;
  seen.add(event.event_id);
  if(seen.size>2000)seen.delete(seen.values().next().value);
  logger.groupCollapsed(`[Ledger Research][${event.level}] ${event.error_code||event.operation}`);
  const method=['ERROR','CRITICAL'].includes(event.level)?'error':event.level==='WARNING'?'warn':'info';
  logger[method](event.message);
  logger.debug({event_id:event.event_id,timestamp:event.timestamp,component:event.component,
   operation:event.operation,details:event.details,suggested_action:event.suggested_action});
  logger.groupEnd();
 }
}
