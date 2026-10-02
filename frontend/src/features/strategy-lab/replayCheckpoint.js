export const checkpointKey='ledger.replay.checkpoint';
export function writeReplayCheckpoint(storage,payload) {
  if(!payload?.anchorTimestamp)throw new Error('No loaded Replay frontier is available to save.');
  const encoded=JSON.stringify(payload);
  try {
    storage.setItem(checkpointKey,encoded);
    if(storage.getItem(checkpointKey)!==encoded)throw new Error('Checkpoint verification failed.');
  }catch {throw new Error('Could not save Replay checkpoint. Browser storage may be full or unavailable. Stay and retry, or explicitly discard.');}
  return encoded;
}
export function replayNeedsGuard(payload,saved) {
  return Boolean(payload&&(payload.position||payload.pendingOrder||payload.pendingClose||JSON.stringify(payload)!==saved));
}
