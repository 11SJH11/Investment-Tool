import test from 'node:test';
import assert from 'node:assert/strict';
import {emitDiagnostics} from '../src/features/strategy-lab/researchDiagnostics.js';

test('research console deduplicates repeated polling and allowlists output',()=>{
 const calls=[],logger=Object.fromEntries(['groupCollapsed','error','warn','info','debug','groupEnd'].map(name=>[name,(...args)=>calls.push([name,...args])]));
 const seen=new Set(),event={event_id:'one',level:'ERROR',error_code:'UNKNOWN_EVIDENCE_REFERENCE',message:'Rejected',secret:'DO_NOT_COPY'};
 emitDiagnostics([event],seen,logger);emitDiagnostics([event],seen,logger);
 assert.equal(calls.filter(row=>row[0]==='error').length,1);
 assert.ok(!JSON.stringify(calls).includes('DO_NOT_COPY'));
 emitDiagnostics([{...event,event_id:'two',level:'WARNING'}],seen,logger);
 assert.equal(calls.filter(row=>row[0]==='warn').length,1);
});
