"""Current-universe discovery snapshots. Never a point-in-time backtest universe."""
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import json
import math
import pandas as pd

TECH_FIELDS = ('close','ema20','ema50','sma200','rsi14','atr','atr_pct','return_5d','return_20d','return_60d','relative_volume','average_volume','average_dollar_volume','distance_20d_high','distance_52w_high','volatility','gap_pct','trend_aligned','volume')
FUND_FIELDS = {'price':'COALESCE(m.price,json_extract(t.payload,\'$.close\'))','market_cap':'f.shares_outstanding*m.price','pe_ratio':'m.price/NULLIF(f.eps_diluted,0)','revenue_growth_yoy':'f.revenue_growth_yoy','net_margin':'f.net_margin','operating_margin':'f.operating_margin','return_on_equity':'f.return_on_equity','free_cash_flow':'f.free_cash_flow'}
FIELDS = {**{k:f"json_extract(t.payload,'$.{k}')" for k in TECH_FIELDS},**FUND_FIELDS}
OPS = {'>':'>','<':'<','>=':'>=','<=':'<=','=':'=','!=':'!='}

def technical_snapshot(frame, now=None):
    now=pd.Timestamp(now or datetime.now(timezone.utc))
    frame=frame.copy();frame['timestamp']=pd.to_datetime(frame['timestamp'],utc=True)
    # Conservative daily completeness: exclude the current New York calendar day.
    frame=frame[frame.timestamp.dt.tz_convert('America/New_York').dt.date < now.tz_convert('America/New_York').date()].sort_values('timestamp').drop_duplicates('timestamp',keep='last')
    if frame.empty:return None
    c,h,l,v=frame.close,frame.high,frame.low,frame.volume
    ema20=c.ewm(span=20,adjust=False,min_periods=20).mean();ema50=c.ewm(span=50,adjust=False,min_periods=50).mean();sma200=c.rolling(200).mean()
    delta=c.diff();gain=delta.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean();loss=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    rsi=100-100/(1+gain/loss);rsi=rsi.mask((loss==0)&(gain>0),100).mask((loss==0)&(gain==0),50)
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1);atr=tr.rolling(14).mean()
    result={'close':c.iloc[-1],'ema20':ema20.iloc[-1],'ema50':ema50.iloc[-1],'sma200':sma200.iloc[-1],'rsi14':rsi.iloc[-1],'atr':atr.iloc[-1],'atr_pct':100*atr.iloc[-1]/c.iloc[-1], 'relative_volume':v.iloc[-1]/v.shift().rolling(20).mean().iloc[-1], 'average_volume':v.rolling(20).mean().iloc[-1], 'average_dollar_volume':(c*v).rolling(20).mean().iloc[-1], 'volatility':c.pct_change(fill_method=None).rolling(20).std().iloc[-1]*math.sqrt(252)*100, 'volume':v.iloc[-1], 'gap_pct':100*(frame.open.iloc[-1]/c.iloc[-2]-1) if len(c)>1 else None}
    for n in (5,20,60):result[f'return_{n}d']=100*(c.iloc[-1]/c.iloc[-n-1]-1) if len(c)>n else None
    for n,key in [(20,'distance_20d_high'),(252,'distance_52w_high')]:result[key]=100*(h.tail(n).max()-c.iloc[-1])/h.tail(n).max() if len(c)>=n else None
    result['trend_aligned']=float(c.iloc[-1]>ema20.iloc[-1]>ema50.iloc[-1]>sma200.iloc[-1]) if len(c)>=200 else None
    result={k:float(value) if value is not None and math.isfinite(float(value)) else None for k,value in result.items()}
    return {**result,'snapshot_at':frame.timestamp.iloc[-1].isoformat(),'history_bars':len(frame)}

class TechnicalScreener:
    def __init__(self,database,market_data,screener=None):
        self.database=database;self.market_data=market_data;self.screener=screener;self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='screener-cache');self.lock=Lock();self.future=None
        self.state={'status':'idle','phase':'idle','automatic':False,'processed':0,'stored':0,'failed':0,'total':0,'price_stored':0,'price_failed':0}
    def close(self):self.pool.shutdown(wait=True,cancel_futures=True)
    def status(self):
        with self.lock:return dict(self.state)
    def ensure_fresh(self):
        """Start safe cache maintenance in the background without hiding cached results.

        Technicals are rebuilt from local daily-bar files only. Price snapshots use
        Alpaca's batch endpoint when configured and are throttled across restarts.
        SEC bulk fundamentals remain explicit because the archive is comparatively
        large and should not be downloaded merely because the app opened.
        """
        now=pd.Timestamp.now(tz='UTC')
        last=self.database.get_setting('screener.maintenance.last_started_at')
        if last:
            try:
                stamp=pd.Timestamp(last);stamp=stamp.tz_localize('UTC') if stamp.tzinfo is None else stamp.tz_convert('UTC')
                if (now-stamp).total_seconds()<1800:return self.status()
            except Exception:pass
        with self.database.connect() as con:
            tech=con.execute('SELECT COUNT(*) AS n,MAX(updated_at) AS updated_at FROM technical_snapshots').fetchone()
            prices=con.execute('SELECT COUNT(*) AS n,MAX(updated_at) AS updated_at FROM market_snapshots').fetchone()
        def due(row,hours):
            if not row or not int(row['n'] or 0) or not row['updated_at']:return True
            stamp=pd.Timestamp(row['updated_at']);stamp=stamp.tz_localize('UTC') if stamp.tzinfo is None else stamp.tz_convert('UTC')
            return (now-stamp).total_seconds()>hours*3600
        demo_mode=str(self.database.get_setting('demo_mode') or '').lower()=='true'
        technical_due=due(tech,12) and not demo_mode
        price_due=bool(not demo_mode and self.screener and self.screener.alpaca is not None and due(prices,4))
        if not technical_due and not price_due:return self.status()
        self.database.set_setting('screener.maintenance.last_started_at',now.isoformat())
        return self.start(include_prices=price_due,automatic=True)
    def start(self,include_prices=False,automatic=False):
        with self.lock:
            if self.future and not self.future.done():return dict(self.state)
            self.state={'status':'queued','phase':'queued','automatic':bool(automatic),'processed':0,'stored':0,'failed':0,'total':0,'price_stored':0,'price_failed':0};self.future=self.pool.submit(self._refresh,bool(include_prices))
            return dict(self.state)
    def _refresh(self,include_prices=False):
        try:
            with self.database.connect() as con:tickers=[r[0] for r in con.execute("SELECT ticker FROM securities WHERE tradable=1 ORDER BY ticker")]
            with self.lock:self.state.update(status='running',phase='technicals',total=len(tickers))
            for ticker in tickers:
                try:
                    provider=self.market_data.provider_for(ticker) if self.market_data else None
                    if provider is None:continue
                    namespace=provider.cache_namespace
                    # Cache only: no provider request, no hidden thousands-symbol download.
                    frame=self.market_data.store.read_bars(namespace,ticker,'1d')
                    result=technical_snapshot(frame) if not frame.empty else None
                    if result:
                        with self.database.connect() as con:con.execute('INSERT INTO technical_snapshots(ticker,payload,source,snapshot_at) VALUES(?,?,?,?) ON CONFLICT(ticker) DO UPDATE SET payload=excluded.payload,source=excluded.source,snapshot_at=excluded.snapshot_at,updated_at=CURRENT_TIMESTAMP',(ticker,json.dumps(result,allow_nan=False),namespace,result['snapshot_at']))
                        with self.lock:self.state['stored']+=1
                except Exception:
                    with self.lock:self.state['failed']+=1
                finally:
                    with self.lock:self.state['processed']+=1
            if include_prices and self.screener and self.screener.alpaca is not None:
                with self.lock:self.state['phase']='prices'
                try:
                    outcome=self.screener.refresh_price_snapshots()
                    with self.lock:
                        self.state['price_stored']=int(outcome.get('stored') or 0)
                        self.state['price_failed']=int(outcome.get('failed') or 0)
                except Exception:
                    with self.lock:self.state['price_failed']=-1
            with self.lock:self.state.update(status='completed',phase='idle')
        except Exception:
            with self.lock:self.state.update(status='failed',phase='idle')
    def query(self,conditions,match='all',security_type='stock',text='',limit=500,offset=0,exchange='',tradable=True,fractionable=None,shortable=None,require_fundamentals=False):
        if match not in {'all','any'} or len(conditions)>30:raise ValueError('Choose ALL or ANY and at most 30 conditions')
        clauses=[];params=[]
        for rule in conditions:
            field=rule.get('field');op=rule.get('operator');other=rule.get('other_field')
            if field not in FIELDS or op not in OPS or (other and other not in FIELDS):raise ValueError('Unsupported screener condition')
            rhs=FIELDS[other] if other else '?'
            if not other:
                try:value=float(rule.get('value'))
                except (TypeError,ValueError):raise ValueError('Condition requires a number') from None
                if not math.isfinite(value):raise ValueError('Condition requires a finite number')
                params.append(value)
            clauses.append(f'({FIELDS[field]} {OPS[op]} {rhs})')
        where=' AND '.join(["1", '('+(' AND ' if match=='all' else ' OR ').join(clauses)+')' if clauses else '1'])
        for key,value in [('tradable',tradable),('fractionable',fractionable),('shortable',shortable)]:
            if value is not None:where+=f' AND s.{key}=?';params.append(int(value))
        if exchange:where+=' AND s.exchange=?';params.append(exchange)
        if require_fundamentals:where+=' AND f.ticker IS NOT NULL'
        if security_type=='stock':where+=" AND s.security_type IN ('common_stock','adr','reit')"
        elif security_type!='all':where+=' AND s.security_type=?';params.append(security_type)
        if text:where+=' AND (s.ticker LIKE ? OR s.name LIKE ?)';params.extend(['%'+text+'%']*2)
        joins='FROM securities s LEFT JOIN fundamental_metrics f ON f.ticker=s.ticker LEFT JOIN market_snapshots m ON m.ticker=s.ticker LEFT JOIN technical_snapshots t ON t.ticker=s.ticker'
        fields=','.join(expression+' AS '+key for key,expression in FIELDS.items())
        with self.database.connect() as con:
            total=con.execute(f'SELECT COUNT(*) {joins} WHERE {where}',params).fetchone()[0]
            items=[dict(r) for r in con.execute(f'SELECT s.ticker,s.name,s.security_type,s.exchange,{fields},t.snapshot_at,t.source AS technical_source,t.updated_at AS snapshot_updated_at,m.timestamp AS price_timestamp {joins} WHERE {where} ORDER BY s.ticker LIMIT ? OFFSET ?',[*params,limit,offset])]
            coverage=dict(con.execute('SELECT COUNT(*) AS available,MAX(snapshot_at) AS latest,MIN(snapshot_at) AS oldest FROM technical_snapshots').fetchone());coverage['universe']=con.execute('SELECT COUNT(*) FROM securities WHERE tradable=1').fetchone()[0]
        now=pd.Timestamp.now(tz='UTC')
        for item in items:item['snapshot_stale']=not item['snapshot_at'] or (now-pd.Timestamp(item['snapshot_at'])).total_seconds()>72*3600
        return {'items':items,'total':total,'coverage':coverage,'job':self.status(),'universe':'current-only','warning':'Historical universe may contain survivorship bias.'}
