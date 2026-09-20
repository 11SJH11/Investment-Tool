// Corrections to older candles, rewinds and prepends require complete replacement.
export function seriesChange(previous,next) {
  if(!previous.length||next.length<previous.length)return {mode:'replace',from:0};
  for(let i=0;i<previous.length-1;i++)if(['time','open','high','low','close','volume'].some(k=>previous[i][k]!==next[i][k]))return {mode:'replace',from:0};
  if(previous.at(-1).time!==next[previous.length-1]?.time)return {mode:'replace',from:0};
  return {mode:'update',from:previous.length-1};
}
