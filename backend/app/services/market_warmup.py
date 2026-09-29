"""Background market-cache warming for favourite/research symbols.

The existing MarketDataService remains the single cache authority.  This service
only asks it to cover a requested range in the background; it never creates a
second OHLCV store.  Continuous futures warm both execution-safe raw/provenance
history and (when configured) the chart representation.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import RLock
import uuid

from app.data.instruments import instrument_spec, normalize_symbol


class MarketWarmupManager:
    def __init__(self, market_data):
        self.market_data = market_data
        self.lock = RLock()
        self.jobs = {}
        self.active_keys = {}
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='market-warm')
        self.closed = False

    def start(self, symbols, *, timeframe='1m', lookback_days=730, refresh=False):
        if self.market_data is None:
            raise RuntimeError('No market data provider is configured')
        days = max(1, min(int(lookback_days), 3650))
        cleaned=[]
        for value in symbols or []:
            symbol=normalize_symbol(value)
            if symbol and symbol not in cleaned: cleaned.append(symbol)
        if not cleaned or len(cleaned)>50:
            raise ValueError('Choose 1 to 50 favourite symbols')
        key=(tuple(cleaned),timeframe,days,bool(refresh))
        with self.lock:
            active=self.active_keys.get(key)
            if active and self.jobs.get(active,{}).get('status') in {'queued','running'}:
                return dict(self.jobs[active])
            job_id=str(uuid.uuid4())
            job={'id':job_id,'symbols':cleaned,'timeframe':timeframe,'lookback_days':days,
                 'refresh':bool(refresh),'status':'queued','completed':0,'total':len(cleaned),'items':[],
                 'created_at':datetime.now(timezone.utc).isoformat()}
            self.jobs[job_id]=job;self.active_keys[key]=job_id
            self.executor.submit(self._run,job_id,key)
            return dict(job)

    def get(self, job_id):
        with self.lock:
            if job_id not in self.jobs: raise ValueError('Cache warm job not found')
            return dict(self.jobs[job_id])

    def _update(self,job_id,**values):
        with self.lock:self.jobs[job_id].update(values)

    def _run(self,job_id,key):
        self._update(job_id,status='running',started_at=datetime.now(timezone.utc).isoformat())
        job=self.get(job_id);results=[]
        for symbol in job['symbols']:
            if self.closed: break
            try:
                end=self.market_data.latest_available_end(symbol,job['timeframe'],datetime.now(timezone.utc))
                start=end-timedelta(days=job['lookback_days'])
                spec=instrument_spec(symbol)
                if spec.security_type=='continuous_future':
                    # Execution history is authoritative for futures backtesting;
                    # this caches dated contracts + roll provenance and the safe
                    # derived continuous snapshot.
                    frame=self.market_data.get_execution_bars(symbol,job['timeframe'],start,end)
                    if getattr(self.market_data.provider_for(symbol),'back_adjust',False):
                        self.market_data.get_bars(symbol,job['timeframe'],start,end,force_refresh=job['refresh'])
                else:
                    frame=self.market_data.get_bars(symbol,job['timeframe'],start,end,force_refresh=job['refresh'])
                results.append({'symbol':symbol,'status':'completed','bars':len(frame),'start':start.isoformat(),'end':end.isoformat()})
            except Exception:
                # Do not expose provider URLs/credential-bearing exception text.
                results.append({'symbol':symbol,'status':'failed','error':'Data update failed; check provider configuration/rate limits and retry.'})
            self._update(job_id,completed=len(results),items=list(results))
        status='completed' if results and all(r['status']=='completed' for r in results) else 'failed'
        self._update(job_id,status=status,completed=len(results),items=results,finished_at=datetime.now(timezone.utc).isoformat())
        with self.lock:self.active_keys.pop(key,None)

    def close(self):
        self.closed=True
        self.executor.shutdown(wait=False,cancel_futures=True)
