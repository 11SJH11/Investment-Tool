"""Official terminal market data, separate from broker reconciliation/execution."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
import math
import re
from types import SimpleNamespace
import pandas as pd
from app.brokers.metatrader5 import MetaTrader5History
from app.brokers.base import BrokerHistoryError
from app.core.safe_errors import ProviderConfigurationError, MissingHistoryError, ProviderUnavailableError
from app.data.providers.base import MarketDataProvider, Quote
from app.data.instruments import instrument_spec, normalize_symbol
from app.data.futures import FAMILIES
from app.data.calendar_front import calendar_front

MONTHS={3:'H',6:'M',9:'U',12:'Z'}
FRAME={'1m':'TIMEFRAME_M1','5m':'TIMEFRAME_M5','15m':'TIMEFRAME_M15','30m':'TIMEFRAME_M30','1h':'TIMEFRAME_H1','4h':'TIMEFRAME_H4','1d':'TIMEFRAME_D1','1w':'TIMEFRAME_W1'}

class MetaTrader5DataProvider(MarketDataProvider):
    key='mt5'
    historical_delay_minutes=0
    historical_feed='mt5-exchange-futures'
    adjustment='unadjusted'
    back_adjust=False
    roll_policy='calendar-front-v1'

    def __init__(self,credentials,environment,mappings,*,module=None):
        self.credentials=dict(credentials);self.environment=environment;self.mappings=dict(mappings);self.module=module
        if not credentials.get('login') or not credentials.get('server'):
            raise ProviderConfigurationError('MT5 market data requires expected MT5_LOGIN and MT5_SERVER to isolate cached account feeds')
        if not self.mappings or any(root not in {'NQ','MNQ'} for root in self.mappings):
            raise ProviderConfigurationError('Configure MT5 futures mappings for NQ and/or MNQ')
        fingerprint=json.dumps([credentials['login'],credentials['server'],environment,mappings],sort_keys=True)
        self.cache_namespace='mt5-futures-calendar-front-v1-raw-'+sha256(fingerprint.encode()).hexdigest()[:24]
        self.last_diagnostics={}

    @contextmanager
    def terminal(self):
        connection=MetaTrader5History(self.credentials,self.environment,module=self.module)
        try:
            connection.connect()
            yield connection._module
        except BrokerHistoryError as exc:
            raise ProviderUnavailableError(str(exc)) from None
        except (ProviderConfigurationError,MissingHistoryError):raise
        except Exception:
            raise ProviderUnavailableError('MT5 market data failed; check terminal connection and symbol history') from None
        finally:connection.close()

    def raw_execution_provider(self):return self

    def broker_symbol(self,ticker):
        spec=instrument_spec(ticker)
        if spec.security_type!='future_contract' or spec.root not in self.mappings:
            raise ProviderConfigurationError('MT5 data requires an explicitly mapped NQ/MNQ dated futures contract')
        match=re.fullmatch(r'(MNQ|NQ)([HMUZ])(\d{2})',ticker)
        if not match:raise ProviderConfigurationError('Use a quarterly contract with a two-digit year, such as NQZ26')
        mapping=self.mappings[spec.root]
        if not isinstance(mapping,dict):raise ProviderConfigurationError('Invalid MT5 futures mapping')
        symbol=mapping.get('contracts',{}).get(ticker)
        if not symbol:
            try:symbol=mapping['template'].format(root=spec.root,month=match[2],yy=match[3],year=2000+int(match[3]))
            except Exception:raise ProviderConfigurationError('MT5 mapping requires contracts or a broker symbol template') from None
        if not isinstance(symbol,str) or len(symbol)>100:raise ProviderConfigurationError('Invalid MT5 broker symbol mapping')
        return symbol

    def validate(self,mt,ticker):
        broker=self.broker_symbol(ticker);info=mt.symbol_info(broker)
        if info is None:raise MissingHistoryError(f'MT5 dated symbol unavailable: {ticker}; check mapping and expired-contract access')
        text=' '.join(str(getattr(info,k,'')) for k in ('name','path','description','exchange')).upper()
        family=FAMILIES[instrument_spec(ticker).root]
        modes={getattr(mt,k) for k in ('SYMBOL_CALC_MODE_FUTURES','SYMBOL_CALC_MODE_EXCH_FUTURES') if hasattr(mt,k)}
        expiry=int(getattr(info,'expiration_time',0));first=int(getattr(info,'start_time',0))
        tick=float(getattr(info,'trade_tick_size',0));value=float(getattr(info,'trade_tick_value',0));size=float(getattr(info,'trade_contract_size',0))
        if any(word in text for word in ('CFD','NAS100','US100','USTEC')) or 'CME' not in text or info.trade_calc_mode not in modes:
            raise ProviderConfigurationError(f'{ticker} is not verified CME futures; CFD aliases are not accepted')
        if not all(math.isfinite(v) for v in (tick,value,size)) or not math.isclose(tick,family.tick_size,rel_tol=1e-7) or not math.isclose(value/tick,family.contract_multiplier,rel_tol=1e-5):
            raise ProviderConfigurationError(f'{ticker} tick/point economics do not match CME specifications')
        if str(getattr(info,'currency_profit','')).upper()!='USD' or expiry<=first or first<=0:
            raise ProviderConfigurationError(f'{ticker} needs USD profit currency and authoritative listing/expiry dates')
        exp=datetime.fromtimestamp(expiry,timezone.utc);match=re.fullmatch(r'(MNQ|NQ)([HMUZ])(\d{2})',ticker)
        if MONTHS.get(exp.month)!=match[2] or exp.year!=2000+int(match[3]):
            raise ProviderConfigurationError(f'{ticker} mapped symbol expiry does not match the dated contract')
        if not mt.symbol_select(broker,True):raise MissingHistoryError(f'MT5 cannot select {ticker} for historical data')
        return info,broker

    def contracts(self,root,start,end):
        if root not in self.mappings:raise ProviderConfigurationError('No MT5 mapping for this futures root')
        result=[]
        with self.terminal() as mt:
            for year in range(start.year,end.year+2):
                for month,code in MONTHS.items():
                    if year==start.year and month<start.month:continue
                    ticker=f'{root}{code}{year%100:02d}'
                    info,_=self.validate(mt,ticker)
                    first=datetime.fromtimestamp(info.start_time,timezone.utc).date();last=datetime.fromtimestamp(info.expiration_time,timezone.utc).date()
                    result.append(SimpleNamespace(ticker=ticker,first_trade_date=first,last_trade_date=last))
                    if last>=end.date():return result
        raise MissingHistoryError('MT5 contract inventory cannot cover the requested dates')

    def get_bars(self,ticker,timeframe,start,end):
        ticker=normalize_symbol(ticker)
        if ticker in self.mappings:ticker+='1!'
        if start.tzinfo is None or end.tzinfo is None:raise ValueError('MT5 dates require an explicit timezone')
        start=start.astimezone(timezone.utc);end=end.astimezone(timezone.utc)
        if start>=end:raise ValueError('start must precede end')
        if timeframe not in FRAME:raise ValueError('Unsupported MT5 timeframe')
        spec=instrument_spec(ticker)
        if spec.security_type=='continuous_future':
            if spec.continuous_rank!=1:raise ValueError('Only front-contract aliases are supported')
            loader=getattr(self,'contract_loader',lambda symbol,tf,a,b:self.get_bars(symbol,tf,a,b))
            frame=calendar_front(self.contracts(spec.root,start,end),spec.root,start,end,lambda symbol,a,b:loader(symbol,timeframe,a,b))
            frame['continuous_alias']=ticker
            return frame
        with self.terminal() as mt:
            info,broker=self.validate(mt,ticker)
            rows=mt.copy_rates_range(broker,getattr(mt,FRAME[timeframe]),start,end)
        if rows is None or len(rows)==0:raise MissingHistoryError(f'MT5 has no {ticker} bars for this range; check terminal Max bars and broker history')
        frame=pd.DataFrame(rows)
        required={'time','open','high','low','close','real_volume'}
        if not required.issubset(frame):raise MissingHistoryError('MT5 returned malformed OHLCV data')
        frame['timestamp']=pd.to_datetime(frame.time,unit='s',utc=True,errors='coerce')
        for field in ('open','high','low','close','real_volume'):frame[field]=pd.to_numeric(frame[field],errors='coerce')
        if frame[['timestamp','open','high','low','close','real_volume']].isna().any().any() or not frame[['open','high','low','close','real_volume']].map(math.isfinite).all().all() or (frame.high<frame[['open','close','low']].max(axis=1)).any() or (frame.low>frame[['open','close']].min(axis=1)).any() or (frame.real_volume<0).any():
            raise MissingHistoryError('MT5 returned invalid OHLCV values; refusing to cache them')
        duplicates=int(frame.timestamp.duplicated().sum())
        if any(len(group[['open','high','low','close','real_volume']].drop_duplicates())>1 for _,group in frame[frame.timestamp.duplicated(False)].groupby('timestamp')):
            raise MissingHistoryError('MT5 returned conflicting duplicate bars')
        frame=frame.drop_duplicates('timestamp').sort_values('timestamp')
        duration={'1m':60,'5m':300,'15m':900,'30m':1800,'1h':3600,'4h':14400,'1d':86400,'1w':604800}[timeframe]
        frame=frame[(frame.timestamp>=start)&(frame.timestamp<end)&(frame.timestamp+pd.Timedelta(seconds=duration)<=datetime.now(timezone.utc))].copy()
        if frame.empty:raise MissingHistoryError('MT5 has no completed bars within the requested range')
        frame['volume']=frame.real_volume # never substitute tick volume for exchange volume
        frame['source_contract']=ticker;frame['provider']=self.key;frame['adjustment_mode']='raw';frame['adjustment_method']='none';frame['price_adjustment']=0.
        frame['roll_method']='dated-contract';frame['roll_schedule_version']='none';frame['contract_last_trade_date']=datetime.fromtimestamp(info.expiration_time,timezone.utc).date().isoformat();frame['roll_effective_at']=''
        self.last_diagnostics={'symbol':ticker,'broker_symbol':broker,'bars':len(frame),'duplicates_removed':duplicates,'first_bar':str(frame.timestamp.min()),'latest_bar':str(frame.timestamp.max()),'volume_type':'real_volume','expiry':frame['contract_last_trade_date'].iloc[0] if len(frame) else None}
        return frame.drop(columns=['time']).reset_index(drop=True)

    def get_quote(self,ticker):
        now=datetime.now(timezone.utc);frame=self.get_bars(ticker,'1m',now-timedelta(days=5),now)
        if frame.empty:raise MissingHistoryError('MT5 quote history unavailable')
        row=frame.iloc[-1];return Quote(ticker,float(row.close),row.timestamp.to_pydatetime())
