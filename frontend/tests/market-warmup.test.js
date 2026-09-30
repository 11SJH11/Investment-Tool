import test from 'node:test';
import assert from 'node:assert/strict';
import {warmActive,warmRange,warmRequest,canResume} from '../src/features/settings/warmupView.js';
import {DEFAULT_PREFS} from '../src/app/preferences.js';

test('warming defaults are opt-in and use a modest explicit history window',()=>{
 assert.equal(DEFAULT_PREFS.keepFavouritesUpdated,false);
 assert.equal(DEFAULT_PREFS.favouriteCacheLookbackDays,30);
 const symbols=['NQ1!'];const request=warmRequest(symbols,30);symbols.push('AAPL');
 assert.deepEqual(request,{symbols:['NQ1!'],timeframe:'1m',lookback_days:30,refresh:false});
 assert.throws(()=>warmRequest(['AAPL'],0));assert.throws(()=>warmRequest(['AAPL'],NaN));
});
test('warm controls distinguish pause, durable resume and provider cooldown',()=>{
 assert(warmActive({status:'pausing'}));assert(!warmActive({status:'completed'}));
 assert(canResume({status:'paused'}));assert(!canResume({status:'running'}));
 assert(!canResume({status:'failed',retry_at:'2026-10-01T12:00:00Z'},Date.parse('2026-10-01T11:00:00Z')));
 assert(canResume({status:'failed',retry_at:'2026-10-01T12:00:00Z'},Date.parse('2026-10-01T12:00:00Z')));
 assert.equal(warmRange(null),'Not yet covered');
 assert.equal(warmRange(['2026-01-01T00:00:00Z','2026-01-08T00:00:00Z']),'2026-01-01 00:00 to 2026-01-08 00:00 UTC');
});
