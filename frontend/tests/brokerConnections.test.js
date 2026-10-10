import test from 'node:test';
import assert from 'node:assert/strict';
import {BROKER_NAMES,canConfigureConnection,canSelectAccount,connectionSummary,connectionHint} from '../src/features/brokers/brokerConnectionUtils.js';

test('Broker names distinguish MT5 and read-only account selection',()=>{
  assert.equal(BROKER_NAMES.mt5,'MetaTrader 5');
  for(const provider of ['tradelocker','mt5']) assert.equal(canSelectAccount(provider),true);
  assert.equal(canSelectAccount('trading212'),false);
  assert.equal(canConfigureConnection('trading212'),true);
  assert.equal(canConfigureConnection('tradovate'),false);
});
test('Disconnected status has priority and MT5 explains local requirements',()=>{
  assert.equal(connectionSummary({configured:true,disconnected:true}),'Disconnected');
  assert.equal(connectionSummary({configured:false}),'Not configured');
  assert.match(connectionHint('mt5'),/machine hosting Ledger/);
  assert.match(connectionHint('mt5'),/MT4 is not supported/);
  assert.match(connectionHint('tradelocker'),/unavailable costs/);
});

test('Robinhood exposes account selection and explicitly read-only OAuth setup',()=>{
  assert.equal(BROKER_NAMES.robinhood,'Robinhood');
  assert.equal(canConfigureConnection('robinhood'),true);
  assert.equal(canSelectAccount('robinhood'),true);
  assert.match(connectionHint('robinhood'),/OAuth/);
  assert.match(connectionHint('robinhood'),/never enables Ledger order execution/);
});
