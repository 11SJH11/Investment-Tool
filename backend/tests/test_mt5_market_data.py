from datetime import datetime, timezone
from types import SimpleNamespace as NS
import pandas as pd
import pytest
from app.data.providers.metatrader5 import MetaTrader5DataProvider
from app.core.safe_errors import MissingHistoryError, ProviderConfigurationError
from app.data.futures import execution_contract
from app.services.market_data import MarketDataService
from app.storage.database import Database
from app.storage.market_store import MarketStore
from app.storage.market_cache_repository import MarketCacheRepository

START=pd.Timestamp('2025-01-02T10:00Z').to_pydatetime();END=pd.Timestamp('2025-01-02T10:03Z').to_pydatetime()
class Terminal:
 SYMBOL_CALC_MODE_EXCH_FUTURES=33;TIMEFRAME_M1=1
 def __init__(self):self.calls=[];self.missing=False;self.cfd=False;self.empty=False
 def initialize(self,*a,**k):return True
 def shutdown(self):pass
 def account_info(self):return NS(login=1,server='CME fixture',currency='USD',trade_mode=0)
 def symbol_select(self,*a):return True
 def symbol_info(self,symbol):
  if self.missing:return None
  year=2000+int(symbol[-2:]);month={'H':3,'M':6,'U':9,'Z':12}[symbol[-3]]
  return NS(name=symbol,path='CFD' if self.cfd else 'Futures/CME',trade_calc_mode=33,trade_tick_size=.25,trade_tick_value=5 if symbol.startswith('NQ') else .5,trade_contract_size=20,currency_profit='USD',start_time=int(pd.Timestamp(f'{year-1}-01-01',tz='UTC').timestamp()),expiration_time=int(pd.Timestamp(f'{year}-{month:02d}-21',tz='UTC').timestamp()))
 def copy_rates_range(self,symbol,tf,start,end):
  self.calls.append((symbol,start,end))
  if self.empty:return []
  return [dict(time=int(t.timestamp()),open=20000,high=20001,low=19999,close=20000,real_volume=100,tick_volume=50) for t in pd.date_range(start,end,freq='min',inclusive='left')]

def provider(mt):return MetaTrader5DataProvider({'login':'1','server':'CME fixture'},'demo',{'NQ':{'template':'{root}{month}{yy}'},'MNQ':{'template':'{root}{month}{yy}'}},module=mt)

def test_conversion_utc_duplicates_and_provenance():
 mt=Terminal();p=provider(mt);original=mt.copy_rates_range;mt.copy_rates_range=lambda *args: (lambda rows:rows+[rows[0]])(original(*args))
 frame=p.get_bars('NQH25','1m',START.astimezone(timezone.utc),END)
 assert len(frame)==3 and str(frame.timestamp.dt.tz)=='UTC'
 assert frame.volume.tolist()==[100]*3 and set(frame.source_contract)=={'NQH25'}
 assert p.last_diagnostics['duplicates_removed']==1

@pytest.mark.parametrize('flag,error',[('missing',MissingHistoryError),('cfd',ProviderConfigurationError),('empty',MissingHistoryError)])
def test_errors_are_explicit(flag,error):
 mt=Terminal();setattr(mt,flag,True)
 with pytest.raises(error):provider(mt).get_bars('NQH25','1m',START,END)

def test_cache_hits_and_missing_tail(tmp_path):
 mt=Terminal();p=provider(mt);db=Database(tmp_path/'db');db.initialize()
 service=MarketDataService(p,MarketStore(tmp_path/'bars'),MarketCacheRepository(db))
 service.get_bars('NQH25','1m',START,END);service.get_bars('NQH25','1m',START,END)
 assert len(mt.calls)==1
 tail=END+pd.Timedelta(minutes=2);service.get_bars('NQH25','1m',START,tail)
 assert len(mt.calls)==2 and mt.calls[-1][1]==END

def test_roll_and_year_boundary():
 p=provider(Terminal());start=pd.Timestamp('2025-12-21T23:58Z').to_pydatetime();end=pd.Timestamp('2025-12-22T00:02Z').to_pydatetime()
 frame=p.get_bars('NQ1!','1m',start,end)
 assert frame.source_contract.tolist()==['NQZ25','NQZ25','NQH26','NQH26']
 assert all(execution_contract('NQ1!',row)==row.source_contract for _,row in frame.iterrows())
 assert set(frame.roll_schedule_version)=={'calendar-front-v1'}

def test_names_never_map_cfds_and_mapping_is_configurable():
 p=provider(Terminal());assert p.broker_symbol('MNQZ26')=='MNQZ26'
 with pytest.raises(ProviderConfigurationError):p.broker_symbol('NAS100')
 p.mappings['NQ']={'contracts':{'NQZ26':'broker-dated-NQ'}}
 assert p.broker_symbol('NQZ26')=='broker-dated-NQ'


@pytest.mark.parametrize('failure',['conflicting','malformed','outside','naive'])
def test_invalid_bars_are_never_accepted(failure):
 mt=Terminal();original=mt.copy_rates_range
 def rows(*args):
  result=original(*args)
  if failure=='conflicting':result.append({**result[0],'close':20000.5})
  if failure=='malformed':result[0]['high']=19998
  if failure=='outside':
   for row in result:row['time']-=86400
  return result
 mt.copy_rates_range=rows
 with pytest.raises((MissingHistoryError,ValueError)):
  provider(mt).get_bars('NQH25','1m',START.replace(tzinfo=None) if failure=='naive' else START,END)

def test_account_namespaces_are_separate_and_missing_native_module_is_safe():
 p=provider(Terminal())
 other=MetaTrader5DataProvider({'login':'2','server':'CME fixture'},'demo',p.mappings)
 assert p.cache_namespace!=other.cache_namespace

def test_invalid_optional_mapping_does_not_prevent_app_start(tmp_path):
 from app.core.config import Settings
 from app.services.container import build_services
 services=build_services(Settings(_env_file=None,LEDGER_DATA_DIR=tmp_path,MT5_MARKET_DATA_ENABLED=True,MT5_FUTURES_MAPPINGS_JSON='bad-json'))
 try:
  assert services.provider_status()['mt5_market_data']['configured'] is False
  assert services.provider_status()['mt5_market_data']['configuration_error']
 finally:services.close()
