from dataclasses import replace

import pytest

from app.brokers.executions import Execution
from app.brokers.mt5_execution_reconciliation import reconcile_order


def execution(identifier='1', **changes):
    return Execution(provider='mt5', environment='demo', account_key='a'*64,
                     external_id=identifier, order_id='100', position_id='200',
                     symbol='XAUUSDs', asset_class='broker_instrument', side='buy',
                     quantity='0.1', price='3000', timestamp='2026-10-20T12:00:00Z',
                     quantity_unit='lots', role='entry', **changes)


def evaluate(fills=None, positions=None, **changes):
    intent = dict(account_key='a'*64, environment='demo',
                  request=dict(symbol='XAUUSDs', side='buy', quantity_lots=.1, stop=2990, target=3010))
    position = dict(symbol='XAUUSDs', side='buy', quantity_lots=.1, stop=2990, target=3010)
    return reconcile_order(intent, [execution()] if fills is None else fills,
                           {'200': position} if positions is None else positions,
                           **(dict(broker_order_id='100', account_key='a'*64,
                                   environment='demo', complete=True) | changes))


def test_positive_order_and_protection_evidence():
    result = evaluate()
    assert result['state'] == 'FILLED_PROTECTED'
    assert not result['retry_allowed'] and not result['execution_enabled']


@pytest.mark.parametrize('changes', [{'broker_order_id': None}, {'complete': False}, {'broker_order_id': 'unknown'}])
def test_unknown_is_never_permission_to_resend(changes):
    result = evaluate(**changes)
    assert result['state'] == 'UNRESOLVED' and not result['retry_allowed']
    assert evaluate(fills=[])['state'] == 'UNRESOLVED'


def test_closed_trade_and_partial_close():
    exit_fill = replace(execution('2'), order_id='101', role='exit', side='sell')
    assert evaluate([execution(), exit_fill], {})['state'] == 'CLOSED'
    half = replace(exit_fill, quantity='0.05')
    position = dict(symbol='XAUUSDs', side='buy', quantity_lots=.05, stop=2990, target=3010)
    result = evaluate([execution(), half], {'200': position})
    assert result['state'] == 'FILLED_PROTECTED' and result['remaining_lots'] == '0.05'


def test_partial_fill_and_multiple_fills():
    half = replace(execution(), quantity='0.05')
    position = dict(symbol='XAUUSDs', side='buy', quantity_lots=.05, stop=2990, target=3010)
    assert evaluate([half], {'200': position})['state'] == 'PARTIAL_PROTECTED'
    assert evaluate([half, replace(half, external_id='2')])['state'] == 'FILLED_PROTECTED'


@pytest.mark.parametrize('field,value', [('stop', 0), ('stop', 2980), ('target', 0)])
def test_protection_must_be_verified(field, value):
    position = dict(symbol='XAUUSDs', side='buy', quantity_lots=.1, stop=2990, target=3010)
    position[field] = value
    assert evaluate(positions={'200': position})['state'] == 'PROTECTION_UNVERIFIED'


@pytest.mark.parametrize('field,value', [('account_key', 'b'*64), ('environment', 'live'), ('provider', 'other')])
def test_account_identity_never_guessed(field, value):
    assert evaluate([replace(execution(), **{field: value})])['state'] == 'IDENTITY_CONFLICT'


def test_duplicate_overfill_and_other_strategy_netting_rejected():
    assert evaluate([execution(), execution()])['state'] == 'EVIDENCE_CONFLICT'
    assert evaluate([replace(execution(), quantity='0.2')])['state'] == 'EVIDENCE_CONFLICT'
    other = replace(execution('2'), order_id='other')
    assert evaluate([execution(), other])['state'] == 'EVIDENCE_CONFLICT'
    assert evaluate(positions={})['state'] == 'UNRESOLVED'


@pytest.mark.parametrize('quantity', ['NaN', '-1', '0', 'Infinity'])
def test_invalid_quantity_is_conflicting_evidence(quantity):
    position = dict(symbol='XAUUSDs', side='buy', quantity_lots=quantity, stop=2990, target=3010)
    assert evaluate(positions={'200': position})['state'] == 'EVIDENCE_CONFLICT'
