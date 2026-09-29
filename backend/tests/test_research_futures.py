import pandas as pd
from app.frame_cache import frames
from app.performance import Profile
from app.services.backtest import BacktestService
from app.services.futures_preflight import preflight
from app.services.market_data import MarketDataService
from app.storage.database import Database
from app.storage.market_cache_repository import MarketCacheRepository
from app.storage.market_store import MarketStore
from app.backtesting.strategies.intraday_baselines import OpeningRangeResearch
from tests.test_continuous_execution import provider, ROLL, marked
from tests.test_intraday_baselines import orb_frame, simulate
from tests.test_research_infrastructure import base


def test_warm_continuous_zero_provider_reads_and_identical_provenance(tmp_path):
    frames.clear();p=provider(tmp_path);db=Database(tmp_path/'isolated.db');db.initialize()
    market=MarketDataService(p,MarketStore(tmp_path/'market'),MarketCacheRepository(db))
    start,end=(ROLL-pd.Timedelta(days=2)).to_pydatetime(),(ROLL+pd.Timedelta(days=1)).to_pydatetime()
    cold=market.get_bars('NQ1!','1m',start,end);calls=len(p.http.calls)
    with Profile() as profile:warm=market.get_bars('NQ1!','1m',start,end)
    pd.testing.assert_frame_equal(cold,warm)
    assert len(p.http.calls)==calls
    assert profile.counts.get('parquet_physical_read',0)==0
    warm.loc[:,'close']=999
    pd.testing.assert_frame_equal(cold,market.get_bars('NQ1!','1m',start,end))
    assert cold.source_contract.tolist()==['NQM6','NQU6']


def test_flat_orb_across_roll_and_full_notional_preflight():
    a=marked(orb_frame('2026-06-10'),'NQM6')
    b=marked(orb_frame('2026-06-11'),'NQU6')
    allbars=pd.concat([a,b],ignore_index=True)
    result=simulate(OpeningRangeResearch(),allbars,symbol='NQ1!',allow_overnight=False)
    assert len(result['trades'])==2
    for trade,source in zip(result['trades'],['NQM6','NQU6']):
        assert trade['symbol']=='NQ1!'
        assert trade['metadata']['source_contract']==source
        assert trade['metadata']['tick_size']==.25
        assert trade['metadata']['contract_multiplier']==20
        assert trade['quantity']==1
        assert trade['gross_pnl']==(trade['exit_price']-trade['entry_price'])*20
    class Service(BacktestService):
        def _load_timeframe(self,*args):return allbars.copy()
    service=Service(None)
    config={**base(), 'symbols':['NQ1!'],'start_date':'2026-06-10','end_date':'2026-06-11'}
    report=preflight(service,config)
    assert report['ready'] and report['tick_value']==5 and report['point_value']==20
    insufficient=preflight(service,{**config,'starting_balance':100})
    assert not insufficient['ready'] and 'full-notional' in insufficient['reason']
    fraction=preflight(service,{**config,'risk_value':.5})
    assert not fraction['ready']


def test_preflight_provider_failure_redacted():
    class Service(BacktestService):
        def _load_timeframe(self,*args):raise RuntimeError('secret-token https://private.example')
    result=preflight(Service(None),{**base(),'symbols':['NQ1!']})
    assert not result['ready'] and 'secret-token' not in str(result)
