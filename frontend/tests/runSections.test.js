import test from 'node:test';
import assert from 'node:assert/strict';
import {createSectionCache} from '../src/features/strategy-lab/runSections.js';
test('section cache deduplicates in-flight fetches, bounds retention and retries failures',async()=>{
 let calls=0;const cache=createSectionCache(async(id,section)=>{calls++;if(id===0)throw Error('missing');return {id,section}},2);
 const a=cache.get(1,'summary');assert.equal(cache.get(1,'summary'),a);await a;assert.equal(calls,1);
 await cache.get(2,'summary');await cache.get(3,'summary');await cache.get(1,'summary');assert.equal(calls,4);
 await assert.rejects(cache.get(0,'summary'));await assert.rejects(cache.get(0,'summary'));assert.equal(calls,6);
});
