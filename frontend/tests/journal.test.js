import test from 'node:test';
import assert from 'node:assert/strict';
import { journalInputToIso } from '../src/features/journal/journalTime.js';
import { sourceLabel, moneyCurrency, pnlSummary } from '../src/features/journal/journalUtils.js';

test('Journal dates convert independently of device timezone',()=>{
  assert.equal(journalInputToIso('2026-06-02T00:30','Europe/London'),'2026-06-01T23:30:00.000Z');
  assert.equal(journalInputToIso('2026-06-01T19:30','America/New_York'),'2026-06-01T23:30:00.000Z');
  assert.equal(journalInputToIso('', 'UTC'),null);
});
test('Journal refuses nonexistent and ambiguous daylight-saving inputs',()=>{
  assert.throws(()=>journalInputToIso('2026-03-29T01:30','Europe/London'),/does not exist/);
  assert.throws(()=>journalInputToIso('2026-10-25T01:30','Europe/London'),/occurs twice/);
  assert.throws(()=>journalInputToIso('2026-11-01T01:30','America/New_York'),/occurs twice/);
  assert.equal(journalInputToIso('2026-10-25T01:30','UTC'),'2026-10-25T01:30:00.000Z');
});
test('Every source has a readable label and unknown currencies cannot crash Journal',()=>{
  for(const source of ['broker_oanda','broker_future_provider','replay','live_manual',undefined])assert.ok(sourceLabel(source));
  assert.match(sourceLabel('broker_oanda'),/OANDA/);
  assert.match(moneyCurrency(2,'legacy currency'),/2.00/);
  const money=pnlSummary({pnl_by_currency:[{currency:'USD',total_pnl:4},{currency:'GBP',total_pnl:3}]});
  assert.match(money,/4.00/);assert.match(money,/3.00/);
});
