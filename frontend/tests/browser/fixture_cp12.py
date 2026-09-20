# Isolated acceptance fixture only. Synthetic equities/Gold and broker adapters;
# NQ is read from an explicitly supplied, previously captured real-bar cache.
import sys,time
from pathlib import Path
from contextlib import asynccontextmanager
sys.path.insert(0,sys.argv[1])
import uvicorn
from fastapi.staticfiles import StaticFiles
from app.core import config
root=Path(sys.argv[2]).resolve();real=Path(sys.argv[4]).resolve()
assert not root.is_relative_to(Path(sys.argv[1]).resolve().parent), 'Use an isolated scratch directory outside the repository'
root.mkdir(parents=True,exist_ok=True)
safe=config.Settings(_env_file=None,LEDGER_DATA_DIR=root/'data',ALPACA_API_KEY='',ALPACA_API_SECRET='',OANDA_ACCESS_TOKEN='',OANDA_ACCOUNT_ID='',MASSIVE_API_KEY='',FRED_API_KEY='',SEC_USER_AGENT='',AUTOCHARTIST_ENABLED=False,TRADING212_API_KEY='',TRADING212_API_SECRET='',BROKER_PROFILES_JSON='[]')
config.get_settings=lambda:safe
from app.main import app
from app.api.strategy_workspace import workspace
from app.services.strategy_workspace import StrategyWorkspace
from app.services.container import build_services
from app.services.broker_connections import BrokerConnections
from app.services.broker_scheduler import BrokerScheduler
from app.services.market_data import MarketDataService
from app.storage.market_store import MarketStore
from app.storage.market_cache_repository import MarketCacheRepository
from app.brokers.base import HistoryBatch
from tests.test_broker_connections import Provider
from tests.test_oanda_journal_import import adapter,history
strategies=root/'strategies';strategies.mkdir(exist_ok=True)
app.dependency_overrides[workspace]=lambda:StrategyWorkspace(strategies)
provider=Provider();now=[time.time()]
class CachedReal:
    key='fixture';historical_delay_minutes=0;historical_feed='isolated-acceptance';adjustment='unadjusted';cache_namespace='cp12-isolated-v1'
    def latest_available_end(self,symbol,timeframe,end):
        import pandas as pd
        return min(end,pd.Timestamp('2026-09-18T20:00:00Z').to_pydatetime())
    def get_bars(self,symbol,timeframe,start,end):
        import pandas as pd
        import numpy as np
        if symbol=='NQ1!':return MarketStore(real).read_bars('cp10-real',symbol,timeframe,start,end)
        freq={'1m':'min','5m':'5min','15m':'15min','30m':'30min','1h':'h','4h':'4h','1d':'B'}[timeframe]
        start=max(pd.Timestamp(start),pd.Timestamp('2025-01-01T00:00Z') if timeframe=='1d' else pd.Timestamp('2026-08-01T00:00Z'))
        timestamps=pd.date_range(start.floor('D'),pd.Timestamp(end),freq=freq)
        if timeframe=='1d':timestamps=timestamps.normalize()+pd.Timedelta(hours=14)
        else:timestamps=timestamps[(timestamps.dayofweek<5)&(timestamps.hour>=13)&(timestamps.hour<20)]
        n=np.arange(len(timestamps));price=(2500 if symbol=='XAUUSD' else 100)+n*.01+np.sin(n/10)*.3
        return pd.DataFrame(dict(timestamp=timestamps,open=price,high=price+.5,low=price-.5,close=price+.1,volume=10000+n%30*100))

def oanda_factory(token,account,env):
    a=adapter(account=account,environment=env);t,o,c,p=history();facts=a._map(t,o,c,p,'USD')
    a.fetch_closed=lambda cursor:HistoryBatch([facts],'30')
    return a
@asynccontextmanager
async def lifespan(app):
    services=build_services(safe)
    cfg=safe.model_copy(update={'oanda_access_token':'synthetic','oanda_account_id':'synthetic','trading212_enabled':True,'trading212_api_key':'synthetic','trading212_api_secret':'synthetic'})
    services.broker_scheduler.close()
    services.broker_connections=BrokerConnections(cfg,services.database,factories={'trading212':provider.factory,'oanda':oanda_factory})
    services.broker_scheduler=BrokerScheduler(services.broker_connections,services.database,clock=lambda:now[0]);services.broker_scheduler.start()
    services.market_data=MarketDataService(CachedReal(),MarketStore(safe.market_data_dir),MarketCacheRepository(services.database))
    services.backtest.market_data=services.market_data
    services.technical_screener.market_data=services.market_data
    with services.database.connect() as con:
        for ticker in ['AAPL','MSFT','NVDA','SPY']:
            con.execute("INSERT OR IGNORE INTO securities(ticker,name,provider,tradable,fractionable,exchange) VALUES(?,?,?,1,1,'NASDAQ')",(ticker,ticker+' fixture','fixture'))
    import pandas as pd
    for ticker in ['AAPL','MSFT','NVDA','SPY']:
        services.market_data.get_bars(ticker,'1d',pd.Timestamp('2025-01-01T00:00Z').to_pydatetime(),pd.Timestamp('2026-09-18T20:00Z').to_pydatetime())
    services.technical_screener.start();services.technical_screener.future.result(timeout=15)
    if not services.journal_repository.list_trades():
        for i in range(1,31):
            day=1+(i%18);result=[-1,0,2][i%3]
            services.journal.create_trade(dict(source='paper_manual',ticker='AAPL' if i%2 else 'MSFT',direction='long',account='Acceptance',opened_at=f'2026-09-{day:02d}T14:{i%6*10:02d}:00Z',closed_at=f'2026-09-{day:02d}T15:{i%6*10:02d}:00Z',entry_price=100,exit_price=100+result,stop_loss=99,take_profit=102,quantity=10,position_currency='GBP' if i%5==0 else 'USD',setup='Pullback' if i%2 else 'Breakout',setup_grade='A' if i%2 else 'B',plan_followed='Yes' if i%2 else 'No',session_time='New York',notes=f'Acceptance note {i}',review_data={'confluences':['Trend'],'mistakes':['Late entry'] if result<0 else []},source_metadata={'mfe_r':2.2,'mae_r':.4}))
    app.state.services=services
    yield
    services.close()
app.router.lifespan_context=lifespan
@app.post('/smoke/advance')
def advance():now[0]+=301;app.state.services.broker_scheduler.tick();return {'ok':True}
@app.get('/smoke/status')
def status():return {'broker_calls':len(provider.calls),'methods':sorted({r.method for r in provider.calls})}
app.mount('/',StaticFiles(directory=sys.argv[3],html=True),name='frontend')
uvicorn.run(app,host='127.0.0.1',port=18096,log_level='error')

