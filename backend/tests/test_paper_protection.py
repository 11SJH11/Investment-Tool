import pytest
from app.forward.paper_protection import PaperProtection
from app.forward.paper_gateway import PaperGateway
from tests.test_forward_deployments import repository
from tests.test_paper_gateway import setup,protected_position,enter,NOW

def test_native_protection_and_restart_never_duplicate_orders(setup):
    gateway,broker,identifier=protected_position(setup)
    manager=PaperProtection(gateway)
    assert manager.maintain(identifier)['status']=='PROTECTED'
    assert len(broker.posts)==2
    restarted=PaperGateway(gateway.database,broker,clock=lambda:NOW)
    assert PaperProtection(restarted).maintain(identifier)['protected']
    assert not restarted.get(identifier)['armed'] and len(broker.posts)==2

def test_partial_entry_waits_for_confirmed_cancel_before_protecting(setup):
    gateway,broker,identifier=setup
    entry=enter(gateway,identifier)
    broker.fill(entry['client_order_id'],1,'partially_filled');broker.quantity='1'
    broker.positions=lambda:[dict(symbol='QQQ',qty='1',avg_entry_price='500')]
    broker.clock=lambda:dict(is_open=True,timestamp=NOW.isoformat(),next_close='2026-01-02T21:00Z')
    broker.cancel=lambda _:broker.orders[entry['client_order_id']].update(status='pending_cancel')
    manager=PaperProtection(gateway)
    assert manager.maintain(identifier)['status']=='ENTRY_CANCEL_PENDING'
    assert len(broker.posts)==1
    broker.orders[entry['client_order_id']]['status']='canceled'
    assert manager.maintain(identifier)['protected']
    assert broker.posts[-1]['qty']=='1'

def test_strategy_exit_waits_for_native_close_cancellation(setup):
    gateway,broker,identifier=protected_position(setup);manager=PaperProtection(gateway)
    protection=manager.maintain(identifier);key=protection['client_order_id']
    broker.cancel=lambda _:broker.orders[key].update(status='pending_cancel')
    assert manager.request_exit(identifier,'strategy_exit')['status']=='CLOSE_CANCEL_PENDING'
    assert len(broker.posts)==2
    broker.orders[key]['status']='canceled'
    assert manager.maintain(identifier)['status']=='EXIT_PENDING'
    assert len(broker.posts)==3 and broker.posts[-1]['time_in_force']=='day'
    assert manager.maintain(identifier)['status']=='EXIT_PENDING' and len(broker.posts)==3

def test_rejected_close_disarms_and_is_not_replaced_automatically(setup):
    gateway,broker,identifier=protected_position(setup);manager=PaperProtection(gateway)
    result=manager.maintain(identifier)
    broker.orders[result['client_order_id']]['status']='rejected'
    for _ in range(2):
        with pytest.raises(ValueError,match='protection ended'):manager.maintain(identifier)
    assert len(broker.posts)==2 and not gateway.get(identifier)['armed']

def test_partial_auction_fill_still_covers_remaining_position(setup):
    gateway,broker,identifier=protected_position(setup);manager=PaperProtection(gateway)
    result=manager.maintain(identifier)
    broker.fill(result['client_order_id'],1,'partially_filled');broker.quantity='1'
    assert manager.maintain(identifier)['protected']
    broker.fill(result['client_order_id'],2);broker.quantity='0'
    assert manager.maintain(identifier)['status']=='FLAT'
    assert len(broker.posts)==2
