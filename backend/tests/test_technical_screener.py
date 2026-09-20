from types import SimpleNamespace
import json
import pandas as pd
import pytest
from app.storage.database import Database
from app.services.technical_screener import TechnicalScreener, technical_snapshot


def bars(n=260):
    c=pd.Series(range(100,100+n),dtype=float)
    return pd.DataFrame(dict(timestamp=pd.date_range('2025-01-01T21:00Z',periods=n,freq='B'),open=c,high=c+2,low=c-2,close=c,volume=1000.))


def test_snapshot_completed_daily_only_and_exact_formulas():
    frame=bars();now=frame.timestamp.iloc[-1]+pd.Timedelta(days=1)
    result=technical_snapshot(frame,now)
    assert result['history_bars']==260
    assert result['atr']==4
    assert result['rsi14']==100
    assert result['relative_volume']==1
    assert result['return_20d']==pytest.approx(100*(359/339-1))
    assert result['sma200']==pytest.approx(sum(range(160,360))/200)
    assert result['trend_aligned']==1
    today=pd.DataFrame([dict(timestamp=now,open=9999,high=9999,low=9999,close=9999,volume=9999)])
    assert technical_snapshot(pd.concat([frame,today]),now)==result


def test_snapshot_missing_history_stays_unavailable():
    result=technical_snapshot(bars(2),pd.Timestamp('2026-01-01',tz='UTC'))
    assert result['sma200'] is None and result['return_60d'] is None
    assert result['relative_volume'] is None and result['trend_aligned'] is None


@pytest.fixture
def scan(tmp_path):
    db=Database(tmp_path/'scan.db');db.initialize()
    with db.connect() as con:
        for ticker,price in [('AAA',30),('BBB',5),('CCC',None)]:
            con.execute("INSERT INTO securities(ticker,name,provider,tradable,fractionable,exchange) VALUES(?,?,?,1,1,'NASDAQ')",(ticker,ticker,'fixture'))
            if price is not None:
                con.execute('INSERT INTO technical_snapshots(ticker,payload,source,snapshot_at) VALUES(?,?,?,?)',(ticker,json.dumps(dict(close=price,ema20=10,return_20d=-5)),'fixture','2025-01-01T21:00:00+00:00'))
    service=TechnicalScreener(db,None)
    yield service
    service.close()


def test_all_any_field_comparison_and_missing_null(scan):
    rules=[dict(field='price',operator='>',other_field='ema20'),dict(field='return_20d',operator='>',value=0)]
    assert scan.query(rules)['total']==0
    result=scan.query(rules,match='any')
    assert [r['ticker'] for r in result['items']]==['AAA']
    assert result['items'][0]['snapshot_stale']
    assert scan.query([dict(field='price',operator='!=',value=5)])['total']==1
    assert scan.query([],fractionable=False)['total']==0
    assert scan.query([],exchange='NASDAQ')['total']==3
    assert scan.query([],text='BBB')['total']==1
    assert scan.query([])['universe']=='current-only'


@pytest.mark.parametrize('rule',[dict(field='price); DROP TABLE securities;',operator='>',value=1),dict(field='price',operator='LIKE',value=1),dict(field='price',operator='>',value='nan'),dict(field='price',operator='>',other_field='absent')])
def test_invalid_condition_rejected(scan,rule):
    with pytest.raises(ValueError):scan.query([rule])
    assert scan.query([])['total']==3


def test_background_refresh_reads_local_cache_only_and_preserves_reinit(scan):
    calls=[]
    def read(namespace,ticker,timeframe):
        calls.append((namespace,ticker,timeframe));return bars()
    scan.market_data=SimpleNamespace(provider_for=lambda _:SimpleNamespace(cache_namespace='fixture'),store=SimpleNamespace(read_bars=read))
    scan.start();scan.future.result(timeout=10)
    assert len(calls)==3 and all(c[2]=='1d' for c in calls)
    assert scan.status()['stored']==3
    before=scan.query([])['items']
    scan.database.initialize();scan.database.initialize()
    assert scan.query([])['items']==before
    scan.market_data.store.read_bars=lambda *args:(_ for _ in ()).throw(RuntimeError('fixture failure'))
    scan.start();scan.future.result(timeout=10)
    assert scan.status()['failed']==3
    assert scan.query([])['items']==before
