from copy import deepcopy
import pytest
from app.research_agent.research_verdict import assess


def trial():
    return dict(status='COMPLETED',control_parity=True,causality={'prefix_match':True},
        robustness={'cells':[dict(status='COMPLETED',summary={'n':40,'average_r':.2},
            comparison={'parent':{'summary':{'average_r':.1}},'removed_large_winners':{'n':0}},
            result={'metrics':{'max_drawdown_pct':-5}})]})


POLICY={'minimum_trades':30,'max_development_drawdown_percent':20}


def test_promising_development_never_grants_acceptance_or_holdout():
    data=trial();before=deepcopy(data)
    result=assess(data,POLICY)
    assert result['verdict']=='PROMISING_DEVELOPMENT'
    assert not result['accepted'] and not result['validation_authorized']
    assert result['evidence_sha256'] and data==before


@pytest.mark.parametrize('change,expected',[
    ('sample','INSUFFICIENT_EVIDENCE'),('zero_cost','INSUFFICIENT_EVIDENCE'),
    ('drawdown','REJECTED_DEVELOPMENT'),('winner_loss','REJECTED_DEVELOPMENT'),
    ('expectancy','REJECTED_DEVELOPMENT'),('causality','INVALID_EXECUTION')])
def test_policy_failures_do_not_become_promotions(change,expected):
    data=trial();cell=data['robustness']['cells'][0]
    if change=='sample':cell['summary']['n']=2
    elif change=='zero_cost':data['robustness']['zero_cost_stress']=True
    elif change=='drawdown':cell['result']['metrics']['max_drawdown_pct']=-21
    elif change=='winner_loss':cell['comparison']['removed_large_winners']['n']=1
    elif change=='expectancy':cell['summary']['average_r']=-.1
    else:data['causality']['prefix_match']=False
    assert assess(data,POLICY)['verdict']==expected
