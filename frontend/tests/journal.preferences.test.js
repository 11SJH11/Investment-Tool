import test from 'node:test';
import assert from 'node:assert/strict';
import { splitOptions, moveOption, TABLE_COLUMNS, DEFAULT_COLUMNS, loadColumns, saveColumns } from '../src/features/journal/journalPreferences.js';

test('explicit paste helper splits newline comma slash, trims and deduplicates', () => {
  assert.deepEqual(splitOptions(' Aligned / Opposed / Not checked\nAligned, Other ,'), ['Aligned','Opposed','Not checked','Other']);
});
test('option reordering preserves exact legacy strings and original array', () => {
  const source = ['A / B','C','D'];
  assert.deepEqual(moveOption(source, 0, 1), ['C','A / B','D']);
  assert.deepEqual(source, ['A / B','C','D']);
  assert.deepEqual(moveOption(source, 0, -1), source);
});
test('column selections survive storage, with invalid keys removed', () => {
  let value=null; const storage={getItem:()=>value,setItem:(_,v)=>{value=v;}};
  assert.deepEqual(loadColumns(storage), DEFAULT_COLUMNS);
  saveColumns(storage,['ticker','environment','ticker','unknown']);
  assert.deepEqual(loadColumns(storage), ['ticker','environment']);
  assert.equal(TABLE_COLUMNS.length,21);
  value='malformed'; assert.deepEqual(loadColumns(storage),DEFAULT_COLUMNS);
  value='[]'; assert.deepEqual(loadColumns(storage),DEFAULT_COLUMNS);
});
test('disabled storage leaves usable default columns', () => {
  const storage={getItem:()=>{throw Error('disabled');},setItem:()=>{throw Error('disabled');}};
  assert.deepEqual(loadColumns(storage),DEFAULT_COLUMNS);
  assert.doesNotThrow(()=>saveColumns(storage,['ticker']));
});
