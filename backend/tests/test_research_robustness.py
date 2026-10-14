from copy import deepcopy
import pytest
from app.research_agent.robustness import plan_windows, execute, simulation_count
from app.research_agent.sandbox import SandboxError
from app.research_agent.sandbox_runs import Approval, ACK


def test_windows_are_fixed_from_chronology_not_results():
    plan={'internal_development_windows':[{'start':'2025-01-01','end':'2025-03-01'},
                                        {'start':'2025-03-02','end':'2025-03-04'}]}
    before=deepcopy(plan)
    assert plan_windows(plan)==[{'start':'2025-01-01','end':'2025-01-07'},{'start':'2025-03-02','end':'2025-03-04'}]
    assert plan==before and simulation_count(plan_windows(plan))==20
    assert simulation_count([])==4


@pytest.mark.parametrize('windows',[
    [{'start':'2025-01-02','end':'2025-01-01'}],
    [{'start':'2025-01-01','end':'2025-01-08'}],
    [{'start':'2025-01-01','end':'2025-01-03'},{'start':'2025-01-03','end':'2025-01-04'}],
    [{'start':'2025-01-03','end':'2025-01-04'},{'start':'2025-01-01','end':'2025-01-02'}],
])
def test_invalid_or_overlapping_windows_rejected(windows):
    with pytest.raises(ValueError):
        Approval(control_parameters={},candidate_parameters={},acknowledgement=ACK,windows=windows)


def test_legacy_approval_defaults_to_no_extra_simulations():
    request=Approval(control_parameters={},candidate_parameters={},acknowledgement=ACK)
    assert request.windows==[]


def test_full_windows_preserve_complete_preregistered_boundaries_and_require_authority():
    plan={'internal_development_windows':[{'start':'2025-01-01','end':'2025-03-31'},
                                         {'start':'2025-04-01','end':'2025-06-30'}]}
    windows=plan_windows(plan,full_windows=True)
    assert windows==plan['internal_development_windows']
    payload=dict(control_parameters={},candidate_parameters={},acknowledgement=ACK,windows=windows)
    with pytest.raises(ValueError,match='seven-day'):
        Approval(**payload,full_period=True)
    with pytest.raises(ValueError,match='authority'):
        Approval(**payload,full_robustness_windows=True)
    approved=Approval(**payload,full_period=True,full_robustness_windows=True)
    assert approved.model_dump(mode='json')['windows']==windows
    assert simulation_count(windows)==20


def test_full_window_cost_runs_do_not_truncate_periods_or_change_warmup():
    _,config,prepare,simulate,save,preparations,*_=fixture()
    config['warmup_start_date']='2024-01-01'
    windows=[{'start':'2025-01-01','end':'2025-03-31'}]
    result=execute(windows,config,prepare,simulate,save,full_windows=True)
    assert len(preparations)==2
    assert all(p['start_date']=='2025-01-01' and p['end_date']=='2025-03-31' and
               p['warmup_start_date']=='2024-01-01' for p in preparations)
    assert [p['commission_per_order'] for p in preparations]==[2,4]
    assert result['version']=='full_window_development_cost_checks_v1'
    assert all(c['control_parity'] for c in result['cells'])


def fixture():
    windows=[{'start':'2025-01-01','end':'2025-01-02'},{'start':'2025-02-01','end':'2025-02-02'}]
    config={'commission_per_order':2,'spread_bps':3,'slippage_bps':4}
    result={'trades':[],'metrics':{},'equity_curve':[]}
    preparations=[];calls=[];saved=[]
    def prepare(payload):
        preparations.append(deepcopy(payload))
        return {},deepcopy(result),payload['start_date']
    def simulate(payload,inputs,child,phase,prefix):
        calls.append((payload,child,phase,prefix))
        return deepcopy(result),['a'] if prefix else ['a','b'],{'source_sha256':'same-source'}
    return windows,config,prepare,simulate,lambda cells:saved.append(deepcopy(cells)),preparations,calls,saved


def test_independent_windows_rerun_actual_costs_and_preserve_source_evidence():
    windows,config,prepare,simulate,save,preparations,calls,saved=fixture()
    result=execute(windows,config,prepare,simulate,save)
    assert len(preparations)==4 and len(calls)==12
    assert [p['commission_per_order'] for p in preparations]==[2,4,2,4]
    assert [p['spread_bps'] for p in preparations]==[3,6,3,6]
    assert [p['slippage_bps'] for p in preparations]==[4,8,4,8]
    assert config=={'commission_per_order':2,'spread_bps':3,'slippage_bps':4}
    assert all(c['control_parity'] and c['prefix_signals_checked']==1 for c in result['cells'])
    assert not result['zero_cost_stress']
    assert 'portfolio' in result['limitation'] and 'total_r' not in result
    assert all(c['result_sha256'] and c['data_fingerprint'] and c['configuration_sha256'] for c in result['cells'])
    assert saved[0][0]['status']=='PREPARING'


@pytest.mark.parametrize('failure',['control','prefix','data','cancel'])
def test_failed_checks_stop_following_windows_and_keep_partial_evidence(failure):
    windows,config,prepare,simulate,save,preparations,calls,saved=fixture()
    def altered_prepare(payload):
        inputs,parent,identity=prepare(payload)
        if failure=='data' and len(preparations)==2:identity='changed'
        return inputs,parent,identity
    def altered_simulate(*args):
        result,trace,provenance=simulate(*args)
        if failure=='control' and not args[2]:result['metrics']['wrong']=1
        if failure=='prefix' and args[4]:trace=['future']
        if failure=='cancel':raise SandboxError('CANCELLED')
        return result,trace,provenance
    with pytest.raises(SandboxError):execute(windows,config,altered_prepare,altered_simulate,save)
    assert len(preparations)<=2 and saved
    assert not any(c.get('window')==2 for cells in saved for c in cells)


def test_zero_costs_do_not_masquerade_as_stress():
    windows,_,prepare,simulate,save,*_=fixture()
    assert execute(windows,{},prepare,simulate,save)['zero_cost_stress']
