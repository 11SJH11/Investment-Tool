from copy import deepcopy
import pytest
from app.research_agent.analysis import analyze, compare, summary


def trade(when, r, pnl, **kwargs):
    return dict(symbol='QQQ',direction='long',entry_time=when,exit_time=when,r_multiple=r,net_pnl=pnl,fees=1,**kwargs)


def run(trades):
    return {'config': {'market_data_fingerprint': 'fixture'}, 'result': {'trades': trades, 'metrics': {}}}


def test_recorded_excursions_keep_missing_and_bound_counts():
    result=summary([trade('2025-01-01T00:00Z',None,None,metadata={'mfe_r_lower_bound':2}),
                    trade('2025-01-01T01:00Z',1,10,metadata={'mfe_r':3,'mae_r':.5})])
    assert result['mfe_n']==2 and result['mfe_lower_bound_n']==1
    assert result['average_mfe_r']==2.5 and result['average_mae_r']==.5 and result['mae_n']==1
    assert result['net_pnl'] is None and result['r_observations']==1
    missing=summary([trade('2025-01-01T00:00Z',None,None)])
    assert missing['average_mfe_r'] is None and missing['total_r'] is None


def test_new_york_boundaries_and_daily_order_do_not_use_utc_month():
    trades=[trade('2025-01-01T01:00Z',1,10),trade('2024-12-31T23:00Z',-1,-10)]
    before=deepcopy(trades);result=analyze(run(trades))
    assert result['breakdowns']['year']['2024']['n']==2
    assert result['breakdowns']['month']['2024-12']['n']==2
    assert result['breakdowns']['entry_hour']['18']['n']==1
    assert result['daily_sequences'][0]['trades'][0]['r_multiple']==-1
    assert result['breakdowns']['trade_number']['1']['total_r']==-1
    assert trades==before


def test_ambiguous_slots_unknown_times_and_missing_fees_are_explicit():
    trades=[trade('2025-01-02T15:00Z',1,10),trade('2025-01-02T15:00Z',-1,-10),trade('2025-01-02T15:00',0,0)]
    trades[0]['fees']=None
    result=analyze(run(trades))
    assert result['daily_sequences'][0]['ambiguous_order']
    assert result['breakdowns']['trade_number']['ambiguous']['n']==2
    assert result['breakdowns']['entry_hour']['unknown']['n']==1
    assert not result['fee_stress']['available']


def test_concentration_and_fee_stress_use_declared_denominators():
    result=analyze(run([trade('2025-01-02T15:00Z',3,30),trade('2025-02-02T15:00Z',1,10),trade('2025-02-03T15:00Z',-1,-20)]))
    assert result['concentration']['top_trade_positive_pnl_share']==.75
    assert result['concentration']['top_month_positive_pnl_share']==.75
    assert result['fee_stress']['rows'][-1]['net_pnl']==17
    assert result['summary']['average_winner_r']==2 and result['summary']['average_loser_r']==-1


def test_removed_trend_winners_and_changed_retained_payoff_are_visible():
    large=trade('2025-01-02T15:00Z',3,30,exit_reason='session_close')
    kept=trade('2025-01-03T15:00Z',2,20)
    parent=run([large,kept,trade('2025-01-04T15:00Z',None,None)])
    child=run([{**kept,'net_pnl':-10,'r_multiple':-1},trade('2025-01-02T16:00Z',-1,-10)])
    result=compare(parent,child)
    assert result['removed_large_winners']['n']==1
    assert result['removed_session_close_winners']['net_pnl']==30
    assert result['retained_large_winners']['n']==1
    assert result['retained_parent']['total_r']==2 and result['retained_child']['total_r']==-1
    assert result['introduced']['n']==1 and result['removed_winners']['n']==1


def test_trade_identity_uses_instant_not_timestamp_spelling():
    a=run([trade('2025-01-02T15:00:00Z',1,10)])
    b=deepcopy(a);b['result']['trades'][0]['entry_time']='2025-01-02T10:00:00-05:00'
    assert compare(a,b)['retained']==1
    b['result']['trades'][0]['entry_time']='2025-01-02T10:00:00'
    with pytest.raises(ValueError,match='timezone-aware'):compare(a,b)
