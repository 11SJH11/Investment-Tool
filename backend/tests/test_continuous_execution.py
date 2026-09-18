from datetime import date, datetime, timezone
from copy import deepcopy

import pandas as pd
import pytest

from app.data.continuous_schedule import VERSION, choose_roll, adjust_continuous
from app.data.providers.massive_futures import MassiveFuturesProvider, FutureContract
from app.data.futures import execution_contract, PROVENANCE_COLUMNS
from app.services.market_data import MarketDataService
from app.services.backtest import BacktestService
from app.services.journal import JournalService
from app.storage.database import Database
from app.storage.market_store import MarketStore
from app.storage.market_cache_repository import MarketCacheRepository
from app.storage.journal_repository import JournalRepository
from app.backtesting.models import EntrySignal
from app.backtesting.strategies.base import Strategy
from app.backtesting.strategies.intraday_baselines import OpeningRangeBreakout, ORB
from tests.test_intraday_baselines import orb_frame, simulate
from tests.test_release_replay import Market
from tests.fakes import FakeJsonHttpClient

FRONT=FutureContract('NQM6','NQ',date(2025,1,1),date(2026,6,19))
NEXT=FutureContract('NQU6','NQ',date(2025,1,1),date(2026,9,18))
ROLL=pd.Timestamp('2026-06-10T22:00Z')


def daily():
    a=pd.DataFrame(dict(timestamp=pd.date_range('2026-06-08T22:00Z',periods=3,freq='D'),
        session_end_date=['2026-06-09','2026-06-10','2026-06-11'],volume=[100,80,60],close=[100.,102.,104.]))
    b=a.copy();b['volume']=[50,120,150];b['close']+=10
    return a,b


def provenance(source='NQM6'):
    return dict(continuous_alias='NQ1!',source_contract=source,roll_schedule_version=VERSION,
        provider='massive',adjustment_mode='raw',adjustment_method='none',price_adjustment=0.)


def marked(frame,source='NQM6'):
    result=frame.copy()
    for k,v in provenance(source).items():result[k]=v
    return result


def test_volume_roll_uses_completed_prior_session_and_not_new_day_values():
    a,b=daily();expected=choose_roll(FRONT,NEXT,a,b)
    assert pd.Timestamp(expected['effective_at'])==ROLL
    assert expected['method']=='prior-session-volume' and expected['close_gap']==10
    a.loc[2,['volume','close']]=999999;b.loc[2,['volume','close']]=0
    assert choose_roll(FRONT,NEXT,a,b)==expected
    # No next session has yet been observed: cannot switch inside the evidence session.
    assert choose_roll(FRONT,NEXT,a.iloc[:2],b.iloc[:2])['method']=='expiry-fallback'


def test_volume_missing_ties_and_window_boundary_are_explicit():
    a,b=daily();b.volume=a.volume
    assert choose_roll(FRONT,NEXT,a,b)['method']=='expiry-fallback'
    assert choose_roll(FRONT,NEXT,a.iloc[:0],b)['method']=='expiry-fallback'
    a,b=daily();a.timestamp-=pd.Timedelta(days=60);b.timestamp-=pd.Timedelta(days=60)
    a.session_end_date=(pd.to_datetime(a.session_end_date)-pd.Timedelta(days=60)).dt.strftime('%Y-%m-%d')
    b.session_end_date=a.session_end_date
    assert choose_roll(FRONT,NEXT,a,b)['method']=='expiry-fallback'


def provider(tmp_path,back_adjust=False):
    a,b=daily()
    def handler(url,params,headers):
        if url.endswith('/contracts'):
            return dict(results=[dict(ticker=c.ticker,product_code=c.product_code,first_trade_date=str(c.first_trade_date),last_trade_date=str(c.last_trade_date)) for c in (FRONT,NEXT)])
        source=a if url.endswith(FRONT.ticker) else b
        if params['resolution']=='1session':
            return dict(results=[dict(window_start=r.timestamp.value,session_end_date=r.session_end_date,open=r.close,high=r.close,low=r.close,close=r.close,volume=r.volume) for r in source.itertuples()])
        stamp=ROLL-pd.Timedelta(hours=1) if url.endswith(FRONT.ticker) else ROLL
        price=104. if url.endswith(FRONT.ticker) else 115.
        return dict(results=[dict(window_start=stamp.value,session_end_date='2026-06-11',open=price,high=price,low=price,close=price,volume=10)])
    return MassiveFuturesProvider('synthetic',back_adjust=back_adjust,http=FakeJsonHttpClient(handler),reference_cache_path=tmp_path/'reference.sqlite')


@pytest.mark.parametrize('tf',['1m','5m','15m','1h'])
def test_provider_schedule_provenance_resolution_and_request_start_independence(tmp_path,tf):
    p=provider(tmp_path)
    full=p.get_bars('NQ1!',tf,(ROLL-pd.Timedelta(days=2)).to_pydatetime(),(ROLL+pd.Timedelta(days=1)).to_pydatetime())
    short=p.get_bars('NQ1!',tf,ROLL.to_pydatetime(),(ROLL+pd.Timedelta(days=1)).to_pydatetime())
    assert full.source_contract.tolist()==['NQM6','NQU6']
    assert full.close.tolist()==[104.,115.]
    assert short.close.tolist()==[115.]
    assert full.roll_schedule_version.eq(VERSION).all()
    assert full.continuous_alias.eq('NQ1!').all() and full.provider.eq('massive').all()
    assert sum(c['params'].get('resolution')=='1session' for c in p.http.calls)==2
    store=MarketStore(tmp_path/'ohlcv');store.write_bars(p.cache_namespace,'NQ1!',tf,full)
    read=store.read_bars(p.cache_namespace,'NQ1!',tf,start=(ROLL-pd.Timedelta(days=2)).to_pydatetime(),end=(ROLL+pd.Timedelta(days=1)).to_pydatetime())
    assert set(PROVENANCE_COLUMNS)<=set(read.columns)
    assert read.source_contract.tolist()==full.source_contract.tolist()


def test_adjustment_uses_daily_close_difference_and_execution_gets_raw(tmp_path):
    p=provider(tmp_path,True);db=Database(tmp_path/'db');db.initialize()
    market=MarketDataService(p,MarketStore(tmp_path/'ohlcv'),MarketCacheRepository(db))
    start,end=(ROLL-pd.Timedelta(days=2)).to_pydatetime(),(ROLL+pd.Timedelta(days=1)).to_pydatetime()
    chart=market.get_bars('NQ1!','1m',start,end)
    assert chart.close.tolist()==[114,115] # daily spread 10, not adjacent bar gap 11
    assert chart.price_adjustment.tolist()==[10,0]
    raw=market.get_execution_bars('NQ1!','1m',start,end)
    assert raw.close.tolist()==[104,115] and raw.adjustment_mode.eq('raw').all()
    assert p.back_adjust # shared chart provider was not mutated
    with pytest.raises(ValueError,match='unadjusted'):execution_contract('NQ1!',chart.iloc[0])


def test_adjustment_without_common_closes_fails_instead_of_inventing_gap():
    frame=pd.DataFrame(dict(timestamp=[ROLL-pd.Timedelta(minutes=1),ROLL],open=[100.,110.],high=[100.,110.],low=[100.,110.],close=[100.,110.]))
    with pytest.raises(ValueError,match='daily closes'):
        adjust_continuous(frame,[dict(effective_at=ROLL.isoformat(),close_gap=None)])


def test_alias_restitches_cached_dated_bars_when_roll_evidence_changes(tmp_path):
    p=provider(tmp_path);original=p.http.handler;missing=[True]
    def delayed(url,params,headers):
        response=original(url,params,headers)
        if missing[0] and params.get('resolution')=='1session' and url.endswith('NQU6'):
            for row in response['results']:row['volume']=1
        return response
    p.http.handler=delayed;db=Database(tmp_path/'db');db.initialize()
    market=MarketDataService(p,MarketStore(tmp_path/'ohlcv'),MarketCacheRepository(db))
    start,end=(ROLL-pd.Timedelta(days=2)).to_pydatetime(),(ROLL+pd.Timedelta(days=1)).to_pydatetime()
    assert market.get_bars('NQ1!','1m',start,end).source_contract.tolist()==['NQM6']
    missing[0]=False
    fresh=market.get_bars('NQ1!','1m',start,end,force_refresh=True)
    assert fresh.source_contract.tolist()==['NQM6','NQU6']
    again=market.get_bars('NQ1!','1m',start,end)
    assert again.source_contract.tolist()==fresh.source_contract.tolist()


@pytest.mark.parametrize('patch',[{'source_contract':'ESM6'},{'source_contract':'NQ1!'},{'provider':'unknown'},
    {'continuous_alias':'ES1!'},{'roll_schedule_version':'unknown'},{'adjustment_mode':'back_adjusted'},
    {'price_adjustment':10},{'source_contract':None}])
def test_alias_requires_valid_raw_same_family_source(patch):
    with pytest.raises(ValueError):execution_contract('NQ1!',{**provenance(),**patch})


def test_alias_orb_matches_dated_economics_and_retains_identities():
    frame=marked(orb_frame())
    result=simulate(OpeningRangeBreakout(),frame,'NQ1!')
    dated=simulate(OpeningRangeBreakout(),frame.drop(columns=list(provenance())),'NQM6')
    trade=result['trades'][0]
    assert trade['entry_price']==103 and trade['exit_price']==111
    assert trade['gross_pnl']==dated['trades'][0]['gross_pnl']==160
    assert trade['r_multiple']==2 and trade['quantity']==1
    assert trade['metadata']['displayed_symbol']=='NQ1!' and trade['metadata']['executed_contract']=='NQM6'


def test_flat_between_sessions_can_transition_and_open_position_cannot():
    a=marked(orb_frame());b=marked(orb_frame('2026-01-06'),'NQU6')
    result=simulate(OpeningRangeBreakout(),pd.concat([a,b],ignore_index=True),'NQ1!')
    assert len(result['trades'])==2
    assert [t['metadata']['executed_contract'] for t in result['trades']]==['NQM6','NQU6']
    a.loc[17,['high','low','open','close']]=103
    with pytest.raises(ValueError,match='Open position crosses'):
        simulate(OpeningRangeBreakout(),pd.concat([a,b],ignore_index=True),'NQ1!')


def test_pending_order_is_cancelled_before_new_contract_fill():
    a=marked(orb_frame());a.loc[16:,'source_contract']='NQU6'
    result=simulate(OpeningRangeBreakout(),a,'NQ1!')
    assert not result['trades']
    assert result['setups'][0]['resolution_reason']=='contract_roll'


@pytest.mark.parametrize('tf',['1m','5m','15m','1h'])
def test_replay_reveals_only_known_contracts_and_retains_provenance(tf):
    m=Market();m.frame=marked(m.frame)
    m.frame.loc[m.frame.timestamp>pd.Timestamp('2026-06-02T14:02Z'),'source_contract']='NQU6'
    args=dict(symbol='NQ1!',timeframe=tf,session='24h',replay_date=date(2026,6,2),start_time='10:02',context_bars=10)
    result=BacktestService(m).replay_bars(**args)
    assert {b['source_contract'] for b in result['source_bars']}=={'NQM6'}
    assert result['bars'][-1]['continuous_alias']=='NQ1!'
    assert 'NQU6' not in str(result)
    m.frame.loc[m.frame.source_contract=='NQU6',['high','close','volume']]=999999
    assert BacktestService(m).replay_bars(**args)==result


def test_replay_journal_idempotent_alias_accounting_and_preservation(tmp_path):
    db=Database(tmp_path/'db');db.initialize();repo=JournalRepository(db);s=JournalService(repo)
    payload=dict(ticker='NQ1!',source='replay',direction='long',entry_price=25000,exit_price=25020,
        stop_loss=24990,quantity=1,external_provider='ledger_replay',external_id='synthetic-roll',
        source_metadata={**provenance('NQU6'),'displayed_symbol':'NQ1!','executed_contract':'NQU6'})
    result=s.create_trade(payload)
    assert result['pnl_amount']==400 and result['r_multiple']==2
    s.update_trade(result['id'],{'notes':'Keep'});again=s.create_trade(payload)
    assert again['id']==result['id'] and again['deduplicated']
    db.initialize();assert repo.get_trade(result['id'])['notes']=='Keep'


def test_offline_comparison_reports_missing_bars_prices_volume_and_contracts():
    from app.data.continuous_comparison import compare_exports
    a=marked(orb_frame()).astype({'close':float});b=a.copy();b.loc[0,'close']+=.25;b.loc[1,'volume']+=3;b.loc[2,'source_contract']='NQU6'
    result=compare_exports(a.iloc[1:],b)
    assert result['matched_timestamps']==17 and len(result['missing_from_ledger'])==1
    assert result['max_absolute_difference']['volume']==3
    assert result['source_contract_mismatches']==1
    assert len(result['rolls']['reference'])==2
    assert compare_exports(a,b)['max_absolute_difference']['close']==.25
    b.timestamp=b.timestamp.dt.tz_localize(None)
    with pytest.raises(ValueError,match='timezone'):compare_exports(a,b)
