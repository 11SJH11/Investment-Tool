from datetime import datetime, timezone

import pandas as pd
import pytest

from app.backtesting.engine import BacktestEngine, _unrealized_total
from app.backtesting.models import BacktestConfig, EntrySignal, ManagePositionSignal
from app.data.futures import FAMILIES, PROVENANCE_COLUMNS, execution_economics
from app.data.instruments import instrument_spec, virtual_symbols
from app.data.providers.massive_futures import MassiveFuturesProvider, _back_adjust
from app.services.chart_data import prepare_chart_bars
from app.services.journal import JournalService
from app.services.market_data import MarketDataService
from app.services.replay_snapshot import aggregate_revealed
from app.storage.database import Database
from app.storage.journal_repository import JournalRepository
from app.storage.market_store import MarketStore
from tests.fakes import FakeJsonHttpClient
from tests.test_phase5_engine import OneLong

NOW = datetime(2026, 9, 1, 14, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize('root,tick,point,value', [
    ('NQ',.25,20,5), ('MNQ',.25,2,.5), ('ES',.25,50,12.5), ('MES',.25,5,1.25),
    ('YM',1,5,5), ('MYM',1,.5,.5), ('RTY',.1,50,5), ('M2K',.1,5,.5),
    ('GC',.1,100,10), ('MGC',.1,10,1), ('CL',.01,1000,10), ('MCL',.01,100,1),
])
def test_family_economics_and_aliases(root, tick, point, value):
    spec = instrument_spec(root+'Z6')
    data = spec.as_dict()
    assert spec.provider_key == 'massive'
    assert data['tick_size'] == tick
    assert data['point_value'] == data['contract_multiplier'] == point
    assert data['tick_value'] == value
    assert data['currency'] == 'USD' and data['execution_supported']
    assert '18:00-17:00' in data['session']
    assert instrument_spec(root+'1!').root == root
    assert not instrument_spec(root+'1!').as_dict()['execution_supported']
    assert root+'1!' in {x['ticker'] for x in virtual_symbols()}


def engine(**config):
    return BacktestEngine(BacktestConfig(**{'starting_balance':1_000_000,
        'sizing_mode':'quantity', 'risk_value':1, **config}))


def position(e=None, direction='long', **overrides):
    e = e or engine()
    return e._open_position(**{'symbol':'NQU6','timestamp':NOW,'raw_open':25000,
        'signal':EntrySignal(direction,24990 if direction=='long' else 25010,
                             25020 if direction=='long' else 24980),
        'balance':1_000_000,'current_exposure':0, **overrides})


@pytest.mark.parametrize('direction,exit_price', [('long',25020),('short',24980)])
def test_twenty_nq_points_are_400_dollars(direction, exit_price):
    e=engine(); p=position(e,direction)
    assert p.initial_risk_amount == 200
    assert p.notional == 500_000
    assert _unrealized_total({'NQU6':p},{'NQU6':exit_price}) == 400
    trade,balance=e._close_position(p,NOW,exit_price,'target',1_000_000,market_fill=False)
    assert trade.gross_pnl == trade.net_pnl == 400
    assert trade.r_multiple == 2 and balance == 1_000_400
    assert trade.pnl_pct == .08


@pytest.mark.parametrize('mode,value,expected', [('cash_risk',399,1),('risk_pct',.0399,1),
    ('quantity',1.9,1),('cash_position',999999,1),('position_pct',99.9,1)])
def test_sizing_in_contracts(mode,value,expected):
    assert position(engine(sizing_mode=mode,risk_value=value)).quantity == expected


def test_notional_cap_does_not_invent_margin_or_round_up():
    assert position(balance=499999) == 'position_size_zero'
    assert position(engine(risk_value=3)).quantity == 2
    assert position(engine(sizing_mode='cash_risk',risk_value=199)) == 'position_size_zero'


def test_partial_exit_contracts_fees_and_final_accounting():
    e=engine(risk_value=2,commission_per_order=2); p=position(e)
    balance=e._apply_management(p,NOW,25010,ManagePositionSignal(reduce_fraction=.5),999998)
    assert balance == 1000196 and p.quantity == 1
    assert p.partial_exits[0]['gross_pnl'] == 200
    # Half of one remaining contract cannot be filled or charged commission.
    assert e._apply_management(p,NOW,25010,ManagePositionSignal(reduce_fraction=.5),balance) == balance
    trade,balance=e._close_position(p,NOW,25020,'target',balance,market_fill=False)
    assert trade.gross_pnl == 600 and trade.fees == 6 and trade.net_pnl == 594
    assert trade.quantity == 2 and trade.exit_price == 25015
    assert trade.r_multiple == 594/400 and balance == 1000594


def test_tick_rejection_and_adverse_cost_rounding():
    e=engine(slippage_bps=.01)
    p=position(e)
    assert p.entry_price == 25000.25
    trade,_=e._close_position(p,NOW,25020,'manual',1_000_000,market_fill=True)
    assert trade.exit_price == 25019.75
    assert position(signal=EntrySignal('long',24990.1,25020)) == 'off_tick_order_price'
    with pytest.raises(ValueError,match='tick'):
        e._apply_management(p,NOW,25000,ManagePositionSignal(new_stop_loss=24995.1),1_000_000)


@pytest.mark.parametrize('symbol', ['NQ1!','M2K1!','ZZZQ6'])
def test_unsupported_execution_fails_explicitly(symbol):
    with pytest.raises(ValueError): execution_economics(symbol)


def bars():
    return pd.DataFrame({'timestamp':pd.date_range(NOW,periods=3,freq='min'),
        'open':[100,100,100], 'high':[100,100,103], 'low':[100,100,100],
        'close':[100,100,102], 'volume':[1,1,1]})


def test_engine_end_to_end_next_open_and_multiplier():
    frame=bars(); frame.timestamp=pd.date_range(NOW,periods=3,freq='5min')
    e=engine(); result=e.run(symbol_frames={'NQU6':{'5m':frame}},
        strategies={'NQU6':OneLong()},primary_timeframe='5m')
    trade=result['trades'][0]
    assert trade['entry_time'].startswith('2026-09-01T14:35')
    assert trade['gross_pnl'] == 40 and trade['r_multiple'] == 2
    assert trade['metadata']['contract_multiplier'] == 20


@pytest.mark.parametrize('column,value', [('source_contract','NQZ6'),('adjustment_method','backward-additive-observed-gap-v1')])
def test_engine_rejects_mixed_contract_or_adjusted_prices(column,value):
    frame=bars(); frame[column]=value
    with pytest.raises(ValueError):
        engine().run(symbol_frames={'NQU6':{'5m':frame}},strategies={'NQU6':OneLong()},primary_timeframe='5m')


def test_calendar_roll_provenance_cache_and_adjustment(tmp_path):
    def handler(url,params,headers):
        if url.endswith('/contracts'):
            return {'results':[{'ticker':t,'product_code':'NQ','first_trade_date':'2025-01-01','last_trade_date':d}
                for t,d in [('NQU6','2026-09-18'),('NQZ6','2026-12-18')]]}
        stamp = '2026-09-18T12:00Z' if url.endswith('NQU6') else '2026-09-21T12:00Z'
        price = 100 if url.endswith('NQU6') else 110
        return {'results':[{'window_start':pd.Timestamp(stamp).value,'open':price,'high':price,
                            'low':price,'close':price,'volume':1}]}
    provider=MassiveFuturesProvider('test-only',http=FakeJsonHttpClient(handler))
    frame=provider.get_bars('NQ1!','1m',datetime(2026,9,18,tzinfo=timezone.utc),datetime(2026,9,22,tzinfo=timezone.utc))
    assert frame.source_contract.tolist() == ['NQU6','NQZ6']
    assert frame.roll_method.tolist() == ['calendar-front']*2
    assert frame.roll_schedule_version.tolist() == ['calendar-front-v1']*2
    assert frame.iloc[1].roll_effective_at == '2026-09-19T00:00:00+00:00'
    assert frame.adjustment_method.tolist() == ['none']*2
    store=MarketStore(tmp_path); store.write_bars(provider.cache_namespace,'NQ1!','1m',frame)
    read=store.read_bars(provider.cache_namespace,'NQ1!','1m',start=datetime(2026,9,18,tzinfo=timezone.utc),end=datetime(2026,9,22,tzinfo=timezone.utc))
    assert set(PROVENANCE_COLUMNS) <= set(read.columns)
    assert read.source_contract.tolist() == frame.source_contract.tolist()
    adjusted=_back_adjust(frame)
    assert adjusted.close.tolist() == [110,110]
    assert adjusted.price_adjustment.tolist() == [10,0]
    assert adjusted.adjustment_method.eq('backward-additive-observed-gap-v1').all()


def test_adjusted_history_never_uses_shared_incremental_cache():
    class Provider:
        back_adjust=True
        def get_bars(self,*args): return bars()
    service=MarketDataService(Provider(),None,None)
    assert len(service.get_bars('NQ1!','1m',NOW,datetime(2026,9,2,tzinfo=timezone.utc))) == 3


@pytest.mark.parametrize('start', ['2026-01-05T23:00Z','2026-07-06T22:00Z'])
def test_session_anchor_provenance_and_revealed_only_aggregation(start):
    frame=bars(); frame.timestamp=pd.date_range(start,periods=3,freq='min')
    frame['source_contract']='NQU6'; frame['roll_method']='dated-contract'; frame['adjustment_method']='none'
    result,_=prepare_chart_bars(frame,'5m','24h',session_profile='futures_24h')
    assert len(result) == 1 and result.iloc[0].timestamp == pd.Timestamp(start)
    assert result.iloc[0].volume == 3 and result.iloc[0].source_contract == 'NQU6'
    replay=aggregate_revealed(frame.iloc[:2],'5m','24h','futures_24h')
    assert replay.iloc[0].high == 100 and replay.iloc[0].volume == 2
    assert replay.iloc[0].is_partial
    frame.loc[2,'source_contract']='NQZ6'
    result,_=prepare_chart_bars(frame,'5m','24h',session_profile='futures_24h')
    assert len(result) == 2 and result.volume.tolist() == [2,1]


def test_journal_futures_accounting_and_legacy_review_preservation(tmp_path):
    db=Database(tmp_path/'journal.db'); db.initialize()
    repo=JournalRepository(db); service=JournalService(repo)
    payload={'ticker':'NQU6','direction':'long','entry_price':25000,'exit_price':25020,
             'stop_loss':24990,'quantity':1,'source':'paper_manual'}
    trade=service.create_trade(payload)
    assert trade['pnl_amount'] == 400 and trade['r_multiple'] == 2
    assert trade['source_metadata']['contract_multiplier'] == 20
    by_notional=service.create_trade({**payload,'position_amount':500000})
    assert by_notional['quantity'] == 1 and by_notional['pnl_amount'] == 400
    with pytest.raises(ValueError,match='whole'):
        service.create_trade({**payload,'quantity':.5})
    with pytest.raises(ValueError,match='USD'):
        service.create_trade({**payload,'position_currency':'GBP'})
    legacy=repo.create_trade({**trade,'ticker':'NQ1!','pnl_amount':20,'source_metadata':{}})
    updated=service.update_trade(legacy['id'],{'notes':'Historical record retained'})
    assert updated['pnl_amount'] == 20 and updated['id'] == legacy['id']
    db.initialize()
    assert repo.get_trade(trade['id'])['pnl_amount'] == 400
