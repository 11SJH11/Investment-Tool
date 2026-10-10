"""Explicit cached provider comparison; never changes routing or account settings."""
from time import perf_counter
import pandas as pd
from app.core.safe_errors import safe_failure, MissingHistoryError, ProviderConfigurationError, ProviderUnavailableError
from app.data.instruments import instrument_spec, normalize_symbol
from app.services.market_data import MarketDataService

DURATIONS={'1m':60,'5m':300,'15m':900,'30m':1800,'1h':3600,'4h':14400,'1d':86400}

def frame_summary(frame,timeframe):
    stamps=pd.to_datetime(frame.timestamp,utc=True)
    gaps=stamps.sort_values().drop_duplicates().diff().dt.total_seconds()
    gap_mask=gaps>DURATIONS[timeframe]
    contracts=[]
    if 'source_contract' in frame:
        for contract,group in frame.groupby('source_contract',sort=False):
            contracts.append({'contract':str(contract),'first':str(group.timestamp.min()),'last':str(group.timestamp.max()),'bars':len(group)})
    return {'bars':len(frame),'duplicate_timestamps':int(stamps.duplicated().sum()),
        'first_bar':str(stamps.min()) if len(frame) else None,'latest_bar':str(stamps.max()) if len(frame) else None,
        'gap_intervals':int(gap_mask.sum()),'largest_gap_seconds':float(gaps.max()) if gaps.notna().any() else None,
        'contracts':contracts,'roll_methods':sorted(set(frame.get('roll_method',pd.Series(dtype=str)).dropna().astype(str))),
        'adjustments':sorted(set(frame.get('adjustment_mode',pd.Series(dtype=str)).dropna().astype(str)))}

def compare_frames(left,right):
    a=left.drop_duplicates('timestamp').set_index('timestamp');b=right.drop_duplicates('timestamp').set_index('timestamp')
    common=a.index.intersection(b.index);differences={}
    for field in ('open','high','low','close','volume'):
        delta=(a.loc[common,field]-b.loc[common,field]).abs().dropna()
        differences[field]={'compared':len(delta),'different':int((delta>0).sum()),'mean_absolute_difference':float(delta.mean()) if len(delta) else None,'max_absolute_difference':float(delta.max()) if len(delta) else None}
    contract_mismatch=None
    if 'source_contract' in a and 'source_contract' in b:
        contract_mismatch=int((a.loc[common,'source_contract']!=b.loc[common,'source_contract']).sum())
    return {'common_timestamps':len(common),'only_massive':len(a.index.difference(b.index)),
        'only_mt5':len(b.index.difference(a.index)),'contract_mismatch_bars':contract_mismatch,'differences':differences}

def diagnose(services,symbol,timeframe,start,end,provider_names=('massive','mt5')):
    symbol=normalize_symbol(symbol);spec=instrument_spec(symbol)
    if spec.root not in {'NQ','MNQ'} or spec.asset_type!='future':raise ValueError('Choose NQ/MNQ futures')
    if timeframe not in DURATIONS or start.tzinfo is None or end.tzinfo is None or not 0<(end-start).total_seconds()<=31*86400:
        raise ValueError('Choose a timezone-aware range of at most 31 days')
    result={'symbol':symbol,'timeframe':timeframe,'start':start.isoformat(),'end':end.isoformat(),'providers':{},
        'note':'Cache-aware elapsed times, not pure network download timings. Gaps include weekends, exchange closures and no-trade intervals. Missing relative timestamps are not proof of missing market data. Historical depth is the observed requested window only. Continuous roll policies may differ; compare dated contracts for like-for-like prices. No default provider is changed.'}
    frames={}
    for name in provider_names:
        started=perf_counter()
        try:
            provider=services.providers.get('market_data_futures' if name=='massive' else 'market_data_mt5')
            # Compare raw executable contract prices rather than adjusted display prices.
            provider=provider.raw_execution_provider() if hasattr(provider,'raw_execution_provider') else provider
            if services.market_data is None:raise RuntimeError('Market data unavailable')
            data=MarketDataService(provider,services.market_data.store,services.market_data.coverage)
            frame=data.get_bars(symbol,timeframe,start,end)
            first=perf_counter()-started;warm=perf_counter();data.get_bars(symbol,timeframe,start,end);warm=perf_counter()-warm
            result['providers'][name]={'status':'connected','first_request_seconds':round(first,4),'cached_request_seconds':round(warm,4),**frame_summary(frame,timeframe)}
            frames[name]=frame
        except Exception as exc:
            category,message,_=safe_failure(exc,default='provider')
            if isinstance(exc,(MissingHistoryError,ProviderConfigurationError,ProviderUnavailableError)):
                message=str(exc)
            if ('market_data_futures' if name=='massive' else 'market_data_mt5') not in services.providers.configured():
                message=f'{name.upper()} market data is not configured; check Settings and backend environment.'
            result['providers'][name]={'status':'unavailable','category':category,'message':message}
    if len(frames)==2:result['comparison']=compare_frames(frames['massive'],frames['mt5'])
    return result
