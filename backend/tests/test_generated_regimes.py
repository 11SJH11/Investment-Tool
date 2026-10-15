from copy import deepcopy
import pytest
from app.research_agent.campaign_policy import CampaignPolicy
from app.research_agent.regime_plan import validate_windows
from app.research_agent.sandbox_runs import Approval, ACK
from app.research_agent.structural_candidates import verify_evidence
from app.research_agent.research_verdict import assess
from tests.test_structural_candidates import evidence

REGIME=dict(name='Synthetic stable session',start='2026-01-02',end='2026-01-02',
            definition='Fixture prices follow a fixed path',evidence_source='Deterministic fixture')

def policy(**changes):
    return CampaignPolicy(code_generation=True,send_development_summaries=True,
                          **{'regime_windows':[REGIME],**changes})

def test_defaults_preserve_existing_campaigns_and_explicit_regimes_roundtrip():
    assert CampaignPolicy().regime_windows==[]
    assert policy().model_dump(mode='json')['regime_windows']==[REGIME]
    approval=Approval(full_period=True,full_robustness_windows=True,regime_windows=[REGIME],
                      control_parameters={},candidate_parameters={},acknowledgement=ACK)
    assert approval.model_dump(mode='json')['regime_windows']==[REGIME]

@pytest.mark.parametrize('changes',[
    {'regime_windows':[REGIME,REGIME]},
    {'regime_windows':[REGIME,{**REGIME,'name':'other'}]},
    {'regime_windows':[{**REGIME,'end':'2026-01-01'}]},
    {'regime_windows':[{**REGIME,'evidence_source':''}]},
    {'structural_evaluation':'bounded_samples'},
    {'structural_robustness':'bounded_samples'},
])
def test_invalid_or_unbounded_plans_rejected(changes):
    with pytest.raises(ValueError):policy(**changes)

@pytest.mark.parametrize('start,end',[('2026-01-03','2026-01-04'),('2026-01-01','2026-01-01')])
def test_development_bounds_reject_other_periods(start,end):
    with pytest.raises(ValueError,match='development range'):validate_windows([REGIME],start,end)

def regime_evidence():
    trial,parent,policy,original=evidence()
    trial['request']['regime_windows']=[deepcopy(REGIME)]
    trial['regime_checks']=deepcopy(trial['robustness'])
    trial['regime_checks']['declared_windows']=[deepcopy(REGIME)]
    return trial,parent,policy,original

def test_regime_evidence_preserves_separate_chronological_checks():
    trial,parent,policy,original=regime_evidence()
    before=deepcopy(trial)
    assert verify_evidence(trial,parent,policy,original)['verdict']=='PROMISING_DEVELOPMENT'
    assert trial==before

@pytest.mark.parametrize('fault',['missing','label','cost','prefix','source','result','comparison','data'])
def test_regime_tampering_blocks_freezing(fault):
    trial,parent,policy,original=regime_evidence()
    group=trial['regime_checks'];cell=group['cells'][0]
    if fault=='missing':group['cells']=[]
    elif fault=='label':group['declared_windows'][0]['name']='Changed'
    elif fault=='cost':cell['cost_multiplier']=3
    elif fault=='prefix':cell['prefix_signals_checked']=0
    elif fault=='source':cell['provenance']={'source_sha256':'changed'}
    elif fault=='result':cell['result']['trades']=[]
    elif fault=='comparison':cell['comparison']['retained']=99
    elif fault=='data':cell['data_fingerprint']='changed'
    with pytest.raises(ValueError):verify_evidence(trial,parent,policy,original)

@pytest.mark.parametrize('fault,verdict',[
    ('missing','INSUFFICIENT_EVIDENCE'),('low_n','INSUFFICIENT_EVIDENCE'),
    ('loss','REJECTED_DEVELOPMENT'),('drawdown','REJECTED_DEVELOPMENT')])
def test_regime_results_participate_in_triage(fault,verdict):
    trial,_,policy,_=regime_evidence()
    cell=trial['regime_checks']['cells'][0]
    if fault=='missing':trial.pop('regime_checks')
    elif fault=='low_n':cell['summary']['n']=0
    elif fault=='loss':cell['summary']['average_r']=-1
    else:cell['result']['metrics']['max_drawdown_pct']=-90
    assert assess(trial,policy)['verdict']==verdict
