from dataclasses import replace
import pandas as pd
import pytest
from app.backtesting.engine import BacktestEngine
from app.backtesting.models import BacktestConfig,Position
from app.backtesting.strategies import strategy_registry
from app.brokers.mt5_execution_ledger import MT5ExecutionLedger
from app.forward.mt5_t01_runtime import T01DecisionRuntime,T02_KEY
from app.storage.database import Database
from tests.test_gold_ifvg_acceptance import fixture
from tests.test_mt5_execution_ledger import policy


@pytest.mark.parametrize('day',['2026-01-04','2026-03-08','2026-11-01'])
@pytest.mark.parametrize('qualifies',[True,False])
def test_t02_decisions_match_backtest_frozen_ratio_and_completed_bar_management(tmp_path,day,qualifies):
    frames=fixture(day,'breakeven')
    if qualifies:
        frames['1m'].loc[0,'high']=3004  # FVG 1 / structural stop distance 9.
        frames['15m'].loc[0,'high']=3004
    expected=BacktestEngine(BacktestConfig(trading_weekdays=(0,1,2,3,4,6))).run(
        symbol_frames={'XAUUSDs':frames},strategies={'XAUUSDs':strategy_registry.create(T02_KEY)},primary_timeframe='1m')
    db=Database(tmp_path/'t02.db');db.initialize()
    ledger=MT5ExecutionLedger(db)
    p=ledger.configure(policy()|dict(strategy_key=T02_KEY,strategy_source_hash=strategy_registry.provenance(T02_KEY)['source_sha256']))
    runner=T01DecisionRuntime(db)
    stream=runner.prepare(ledger,p['id'],symbol='XAUUSDs',stream_key='t02',timestamp_policy='verified_utc')
    records=[]
    for index,row in enumerate(frames['1m'].iloc[:60].to_dict('records')):
        if index==49:runner=T01DecisionRuntime(db)
        bar=dict(row,timestamp=row['timestamp'].isoformat(),available_at=(row['timestamp']+pd.Timedelta(minutes=1)).isoformat())
        records.append(runner.step(stream['id'],bar,observed_at=bar['available_at'],equity=10000))
    assert all(r['result'] is None for r in records[:-1])
    if not qualifies:
        assert records[-1]['result'] is None and not expected['trades']
        return
    assert len(expected['trades'])==1
    trade=expected['trades'][0];entry=records[-1]['result']['signal']
    assert entry['stop_loss']==trade['stop_loss']==3010
    assert entry['metadata']['ifvg_fvg_to_stop_ratio_at_signal']==pytest.approx(1/9)
    assert pd.Timestamp(records[-1]['not_before'])==pd.Timestamp(trade['entry_time'])
    assert entry['target_r']==1 and trade['r_multiple']==0
    position=Position(symbol='XAUUSDs',direction='short',entry_time=pd.Timestamp(trade['entry_time']),entry_price=3001,quantity=1,stop_loss=3010,take_profit=2992,initial_risk_per_share=9,initial_risk_amount=9,metadata=entry['metadata'])
    row=frames['1m'].iloc[60].to_dict()
    bar=dict(row,timestamp=row['timestamp'].isoformat(),available_at=(row['timestamp']+pd.Timedelta(minutes=1)).isoformat())
    result=runner.step(stream['id'],bar,observed_at=bar['available_at'],equity=10000,position=position,attribution_verified=True)
    assert result['result']['kind']=='manage' and result['result']['signal']['new_stop_loss']==3001
    assert pd.Timestamp(result['not_before'])==frames['1m'].timestamp.iloc[61]
    assert not result['execution_enabled']
    with pytest.raises(ValueError,match='immutable'):
        runner.prepare(ledger,p['id'],symbol='XAUUSDs',stream_key='t02',timestamp_policy='verified_utc',parameters={'direction':'long'})
    with pytest.raises(ValueError,match='frozen'):
        runner.prepare(ledger,p['id'],symbol='XAUUSDs',stream_key='different',timestamp_policy='verified_utc',parameters={'target_r':3})
