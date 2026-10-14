from copy import deepcopy
import pytest
from app.research_agent.analysis import compare,digest,summary
from app.research_agent.structural_candidates import verify_evidence


def evidence():
    trades=[dict(symbol='QQQ',direction='long',entry_time='2026-01-02T14:31:00Z',
        exit_time='2026-01-02T14:32:00Z',r_multiple=1,net_pnl=10,exit_reason='target')]
    result={'trades':trades,'metrics':{'max_drawdown_pct':0},'equity_curve':[]}
    identity={'market_data_fingerprint':'fixture'}
    comparison=compare({'config':identity,'result':result},{'config':identity,'result':result})
    parent={'snapshot_hash':'parent','snapshot':{'data_fingerprint':'fixture','result_digest':comparison['parent']['result_digest']}}
    cells=[dict(window=1,start='2026-01-02',end='2026-01-02',cost_multiplier=cost,
        status='COMPLETED',control_parity=True,prefix_signals_checked=1,data_fingerprint='fixture',
        parent_result=deepcopy(result),result=deepcopy(result),parent_result_sha256=digest(result),
        result_sha256=digest(result),summary=summary(trades),comparison=deepcopy(comparison)) for cost in (1,2)]
    trial=dict(status='COMPLETED',candidate_hash='parent',control_parity=True,
        causality={'prefix_match':True},provenance={'data_fingerprint':'fixture'},
        request={'full_period':True,'full_robustness_windows':True,'windows':[{'start':'2026-01-02','end':'2026-01-02'}]},
        result=result,result_sha256=digest(result),summary=summary(trades),comparison=comparison,
        robustness={'status':'COMPLETED','cells':cells,'zero_cost_stress':False})
    return trial,parent,{'minimum_trades':1,'max_development_drawdown_percent':20},deepcopy(result)


def test_verified_development_freeze_evidence_never_grants_holdout_or_execution():
    trial,parent,policy,original=evidence();before=deepcopy(trial)
    decision=verify_evidence(trial,parent,policy,original)
    assert decision['verdict']=='PROMISING_DEVELOPMENT'
    assert not decision['accepted'] and not decision['validation_authorized']
    assert trial==before


@pytest.mark.parametrize('fault',['result','summary','comparison','missing_cost','cost_result',
                                 'cost_comparison','prefix','parent','data','bounded','zero_cost','low_n','cost_source'])
def test_changed_or_incomplete_evidence_cannot_be_frozen(fault):
    trial,parent,policy,original=evidence()
    if fault=='result':trial['result']['metrics']['max_drawdown_pct']=-90
    elif fault=='summary':trial['summary']['average_r']=99
    elif fault=='comparison':trial['comparison']['retained']=9
    elif fault=='missing_cost':trial['robustness']['cells'].pop()
    elif fault=='cost_result':trial['robustness']['cells'][0]['result']['trades'].clear()
    elif fault=='cost_comparison':trial['robustness']['cells'][0]['comparison']['retained']=99
    elif fault=='prefix':trial['robustness']['cells'][0]['prefix_signals_checked']=0
    elif fault=='parent':trial['candidate_hash']='other'
    elif fault=='data':trial['provenance']['data_fingerprint']='other'
    elif fault=='bounded':trial['request']['full_period']=False
    elif fault=='zero_cost':trial['robustness']['zero_cost_stress']=True
    elif fault=='low_n':policy['minimum_trades']=30
    elif fault=='cost_source':trial['robustness']['cells'][0]['provenance']={'source_sha256':'other'}
    with pytest.raises(ValueError):verify_evidence(trial,parent,policy,original)
