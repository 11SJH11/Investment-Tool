from copy import deepcopy
import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.test_research_trials import research
from tests.test_research_author import Model
from tests.test_backtest_jobs import wait_for
from app.research_agent.author import CodeAuthor, CONSENT
from app.research_agent.campaigns import Campaigns
from app.research_agent.campaign_policy import CampaignPolicy, DatasetPolicy
from app.research_agent.campaign_projects import provision
from app.research_agent.director import ResearchDirector, permitted
from app.research_agent.repository import ResearchRepository
from app.research_agent.sandbox_runs import SandboxRuns


class SandboxFixture:
    def __init__(self):
        self.docker=SimpleNamespace(image=lambda:'fixture-image')
        self.thread=None
        self.calls=[]
        self.items={}

    def approve(self,pid,cid,did,payload):
        self.calls.append((pid,cid,did,payload))
        result=dict(id='sandbox-fixture',status='COMPLETED',control_parity=True,
                    causality={'prefix_match':True},summary={'n':0})
        self.items[result['id']]=result
        return result

    def get(self,identifier):return self.items[identifier]
    def cancel(self,*args):pass


@pytest.fixture
def structural(research,monkeypatch):
    db,_,original,_,jobs,backtest=research
    campaigns=Campaigns(db)
    policy=CampaignPolicy(code_generation=True,send_development_summaries=True,
                          dataset=DatasetPolicy(warmup_sessions=1,min_development_sessions=2,min_holdout_sessions=1,internal_windows=2))
    campaign=campaigns.create(dict(request_key='structural',mode='IMPROVE_STRATEGY',strategy_key=original['strategy_key'],policy=policy.model_dump()))
    campaign=campaigns.prepare(campaign['id'],[dict(family_id='fixture',strategy_key=original['strategy_key'],reason='Structural fixture')],
        [dict(symbol='QQQ',timeframe='1m',provider_namespace='fixture',source_fingerprint='fixture',completed_through='2026-01-04',
              sessions=['2026-01-01','2026-01-02','2026-01-03','2026-01-04'])])
    links=provision(db,campaign['id'])
    model=Model()
    monkeypatch.setattr('app.research_agent.author.archived_parent',lambda *args:dict(source='SYNTHETIC_PARENT',sha256='fixture'))
    author=CodeAuthor(db,model)
    sandbox=SandboxFixture()
    services=SimpleNamespace(database=db,backtest_jobs=jobs,research_author=author,research_sandbox=sandbox,
                             research_loop=SimpleNamespace(committee=SimpleNamespace(model=model)))
    director=ResearchDirector(services,start_thread=False)
    configs={p['project_id']:dict(starting_balance=10000,risk_value=1,commission_per_order=0,
                               spread_bps=0,slippage_bps=0,max_leverage=1,strategy_params={'skip':0}) for p in links}
    yield director,campaign,configs,model,backtest
    director.close()
    author.close()


def until(director,cid,state=None,phase=None):
    def done():
        director.tick()
        item=director.campaigns.get(cid)
        return item['status']==state if state else item['execution']['entries'][0]['state']==phase
    wait_for(done)
    return director.campaigns.get(cid)


def test_campaign_authors_then_dispatches_existing_sandbox_without_browser(structural):
    director,campaign,configs,model,backtest=structural
    start=director.start_baselines(campaign['id'],configs,structural=True)
    result=until(director,campaign['id'],state='DEVELOPMENT_COMPLETE')
    entry=result['execution']['entries'][0]
    assert entry['state']=='COMPLETED',result
    assert entry['structural_result']['control_parity']
    assert len(model.calls)==4 and len(director.services.research_sandbox.calls)==1
    assert result['reserved']==start['reserved']
    assert result['reserved']['simulations']==22 and result['reserved']['children']==1
    assert entry['robustness_windows']==[{'start':'2026-01-02','end':'2026-01-02'},{'start':'2026-01-03','end':'2026-01-03'}]
    assert director.services.research_sandbox.calls[0][3]['windows']==entry['robustness_windows']
    assert result['reserved']['llm_calls']==4
    parent=backtest.runs.get(entry['run_id'])
    reference=backtest.runs.get(entry['reference_run_id'])
    assert parent['config']['end_date']=='2026-01-03'
    assert reference['config']['start_date']=='2026-01-02'
    assert reference['config']['end_date']==parent['config']['end_date']=='2026-01-03'
    assert reference['config']['warmup_start_date']==parent['config']['warmup_start_date']
    assert entry['full_period'] is True
    assert entry['full_robustness_windows'] is True
    assert director.services.research_sandbox.calls[0][3]['full_robustness_windows'] is True
    assert entry['run_id']!=entry['reference_run_id']
    a=ResearchRepository(director.database).get(entry['project_id'])
    b=ResearchRepository(director.database).get(entry['reference_project_id'])
    assert {d['id'] for d in a['datasets']}=={d['id'] for d in b['datasets']}
    assert any(d['state']=='LOCKED_HOLDOUT' for d in b['datasets'])
    with director.database.connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS agent_sandbox_runs(id TEXT PRIMARY KEY, document TEXT)')
        c.execute('INSERT INTO agent_sandbox_runs VALUES (?,?)',
                  (entry['sandbox_id'], json.dumps(director.services.research_sandbox.get(entry['sandbox_id']))))
    report = director.campaigns.report(campaign['id'])['morning_report']['families'][0]
    history = report['search_history']
    assert history['debt']['structural_author_requests'] == 1
    record = next(r for r in history['records'] if r['kind'] == 'STRUCTURAL')
    assert record['preregistration'] == 'VERIFIED'
    assert record['sandbox_id'] == entry['sandbox_id']
    assert record['development_outcome'] == entry['research_decision']
    director.tick()
    assert len(model.calls)==4 and len(director.services.research_sandbox.calls)==1


def test_author_rejection_does_not_dispatch_or_spend_again_after_restart(structural):
    director,campaign,configs,model,_=structural
    model.reject=True
    director.start_baselines(campaign['id'],configs,structural=True)
    result=until(director,campaign['id'],state='DEVELOPMENT_COMPLETE')
    assert result['execution']['entries'][0]['state']=='RESEARCH_STOPPED'
    assert len(model.calls)==3 and not director.services.research_sandbox.calls
    restarted=ResearchDirector(director.services,start_thread=False)
    try:
        restarted.tick()
        assert len(model.calls)==3
    finally:restarted.close()


def test_second_structural_iteration_sees_previous_evidence_and_rejects_duplicate_code(structural):
    director,campaign,configs,model,_=structural
    with director.database.connect() as c:
        item=director.campaigns._get(c,campaign['id'])
        item['request']['policy']['max_structural_hypotheses_per_family']=2
        director.campaigns._save(c,item)
    start=director.start_baselines(campaign['id'],configs,structural=True)
    result=until(director,campaign['id'],state='DEVELOPMENT_COMPLETE')
    entry=result['execution']['entries'][0]
    assert start['reserved']['llm_calls']==8 and start['reserved']['simulations']==42
    assert len(model.calls)==8 and len(director.services.research_sandbox.calls)==1
    assert entry['reason']=='duplicate_structural_source_no_retest'
    assert model.calls[4][1]['prior_structural_attempts'][0]['sandbox_id']=='sandbox-fixture'
    assert entry['structural_attempts'][0]['decision']['verdict']=='INVALID_EXECUTION' or entry['structural_attempts'][0]['decision']['verdict']=='INSUFFICIENT_EVIDENCE'


def test_campaign_pause_mid_model_call_revokes_author_and_no_docker(structural):
    director,campaign,configs,model,_=structural
    def pause(role,result,usage):director.control(campaign['id'],'pause')
    model.mutate=pause
    director.start_baselines(campaign['id'],configs,structural=True)
    item=until(director,campaign['id'],state='PAUSED')
    director.services.research_author.thread.join(timeout=15)
    entry=item['execution']['entries'][0]
    assert not permitted(director.database,entry['reference_project_id'])
    assert not director.services.research_sandbox.calls and len(model.calls)==1
    director.control(campaign['id'],'resume')
    until(director,campaign['id'],state='DEVELOPMENT_COMPLETE')
    assert len(model.calls)==1


def test_manual_author_cannot_bypass_campaign_allocation(structural):
    director,campaign,configs,model,_=structural
    start=director.start_baselines(campaign['id'],configs,structural=True)
    item=until(director,campaign['id'],phase='AUTHOR')
    pid=item['execution']['entries'][0]['reference_project_id']
    with pytest.raises(ValueError,match='Director allocation'):
        director.services.research_author.start(pid,dict(request_key='bypass',consent=CONSENT))
    assert not model.calls
    from app.research_agent.committee import Committee
    parent=start['execution']['entries'][0]['project_id']
    with pytest.raises(ValueError,match='call budget'):
        Committee(director.database,model).review(parent,'unreserved')


def test_forged_campaign_sandbox_parameters_rejected(structural):
    from app.research_agent.structural import sandbox_authorized
    director,campaign,configs,_,_=structural
    director.start_baselines(campaign['id'],configs,structural=True)
    item=until(director,campaign['id'],phase='SANDBOX')
    entry=item['execution']['entries'][0]
    project=ResearchRepository(director.database).get(entry['reference_project_id'])
    with pytest.raises(ValueError,match='differs'):
        sandbox_authorized(director.database,project,entry['reference_id'],entry['draft_id'],{})
    from app.research_agent.sandbox_runs import ACK
    with pytest.raises(ValueError,match='differs'):
        sandbox_authorized(director.database,project,entry['reference_id'],entry['draft_id'],dict(
            control_parameters={'skip':0,'research_feature_enabled':False},
            candidate_parameters={'skip':0,'research_feature_enabled':True},
            timeout_seconds=min(600,entry['max_minutes']*60),acknowledgement=ACK,windows=[]))


def test_structural_budget_reserves_all_cost_and_window_runs_before_dispatch(structural):
    director,campaign,configs,model,_=structural
    with director.database.connect() as c:
        item=director.campaigns._get(c,campaign['id'])
        item['request']['policy']['budget']['simulations']=21
        director.campaigns._save(c,item)
    with pytest.raises(ValueError,match='budget exhausted'):
        director.start_baselines(campaign['id'],configs,structural=True)
    assert not model.calls and not director.services.research_sandbox.calls
    assert 'execution' not in director.campaigns.get(campaign['id'])


def test_legacy_campaign_policy_keeps_original_bounded_reference(structural):
    director,campaign,configs,_,_=structural
    with director.database.connect() as c:
        item=director.campaigns._get(c,campaign['id'])
        item['request']['policy'].pop('structural_evaluation',None)
        director.campaigns._save(c,item)
    started=director.start_baselines(campaign['id'],configs,structural=True)
    entry=started['execution']['entries'][0]
    assert not entry['full_period']
    assert entry['reference_payload']['end_date']==entry['reference_payload']['start_date']
    assert not entry['reference_payload'].get('warmup_start_date')


def test_existing_full_period_policy_does_not_gain_full_window_authority(structural):
    director,campaign,configs,_,_=structural
    with director.database.connect() as c:
        item=director.campaigns._get(c,campaign['id'])
        item['request']['policy'].pop('structural_robustness',None)
        director.campaigns._save(c,item)
    started=director.start_baselines(campaign['id'],configs,structural=True)
    entry=started['execution']['entries'][0]
    assert entry['full_period']
    assert not entry['full_robustness_windows']


@pytest.mark.skipif(os.environ.get('LEDGER_TEST_DOCKER')!='1',reason='Opt-in complete campaign Docker acceptance')
@pytest.mark.parametrize('promising',[False,True,'automatic','simpler_parent','iterate_restart'])
def test_campaign_full_loop_with_mock_model_and_real_docker(structural,promising):
    director,campaign,configs,model,backtest=structural
    if promising:
        with director.database.connect() as c:
            item=director.campaigns._get(c,campaign['id'])
            item['request']['policy']['minimum_trades']=1
            if promising not in {'simpler_parent', 'iterate_restart'}:
                # Historical campaigns retain their original freeze contract.
                item['request']['policy'].pop('structural_simplification', None)
            if promising=='automatic':item['request']['policy']['holdout']='one_frozen_candidate'
            if promising=='iterate_restart':item['request']['policy']['max_structural_hypotheses_per_family']=2
            director.campaigns._save(c,item)
        # This synthetic four-day calendar includes Saturday; explicitly enable
        # its fixture session rather than weakening the minimum-sample gate.
        for config in configs.values():
            config['commission_per_order']=.01
            config['trading_weekdays']=list(range(7))
        def keep_entries(role,result,usage):
            second = sum(r == 'CodeAuthor' for r, _ in model.calls) > 1
            if role=='Researcher' and promising=='iterate_restart':
                next_attempt = sum(r == 'Researcher' for r, _ in model.calls) > 1
                result.update(description='Neutral synthetic gate' if next_attempt else 'Synthetic entry rejection',
                              feature='Keep baseline entries' if next_attempt else 'Suppress all entries',
                              expected_result='Same trade path' if next_attempt else 'No entries',
                              falsification='Changed trades' if next_attempt else 'Any entry')
            if role=='CodeAuthor' and (promising!='iterate_restart' or second):
                result['source']=result['source'].replace("if self.params['research_feature_enabled']:return None",'if False:return None')
        model.mutate=keep_entries
    original=backtest.prepare
    def prepare(payload,**kwargs):
        from app.research_agent.workflow import validate_submission
        def validate(db,data):
            if data.get('research_project_id'):validate_submission(db,data)
        with patch('tests.test_research_trials.validate_submission',validate):
            data=original(payload,**kwargs)
        import pandas as pd
        delta=pd.Timestamp(payload['start_date'])-pd.Timestamp('2026-01-02')
        data['frames_by_symbol']['QQQ']['1m']['timestamp']+=delta
        data['start']+=delta;data['end']+=delta
        return data
    backtest.prepare=prepare
    runner=SandboxRuns(director.database,backtest)
    director.services.research_sandbox=runner
    restarted = None
    try:
        started = director.start_baselines(campaign['id'],configs,structural=True)
        # Existing wait_for uses a short timeout, so wait for the durable dispatch
        # first and then join the bounded Docker task independently.
        until(director,campaign['id'],phase='SANDBOX')
        director.tick()
        runner.thread.join(timeout=90)
        assert not runner.thread.is_alive()
        if promising=='iterate_restart':
            director.tick()
            checkpoint = director.campaigns.get(campaign['id'])
            prior = checkpoint['execution']['entries'][0]
            assert prior['state']=='AUTHOR' and len(prior['structural_attempts'])==1
            assert prior['structural_attempts'][0]['decision']['verdict']=='INSUFFICIENT_EVIDENCE'
            assert len(model.calls)==4
            director.close()
            restarted = ResearchDirector(director.services,start_thread=False)
            director = restarted
            until(director,campaign['id'],phase='SANDBOX')
            director.tick()
            runner.thread.join(timeout=90)
            assert not runner.thread.is_alive()
        result=until(director,campaign['id'],state='DEVELOPMENT_COMPLETE')
        entry=result['execution']['entries'][0]
        assert entry['state']=='COMPLETED',json.dumps(entry,indent=2)
        expected_closeout = ('ABANDONED_DEVELOPMENT' if promising in {'simpler_parent','iterate_restart'} else
                             'FROZEN_REQUIRES_VALIDATION' if promising else 'INCONCLUSIVE')
        assert entry['disposition']['outcome'] == expected_closeout
        assert director.campaigns.report(campaign['id'])['morning_report']['families'][0]['disposition'] == entry['disposition']
        assert entry['structural_result']['causality']['prefix_match']
        trial=runner.get(entry['sandbox_id'])
        assert trial['reserved_runs']==20
        assert len(trial['robustness']['cells'])==4
        assert all(cell['status']=='COMPLETED' and cell['control_parity'] for cell in trial['robustness']['cells'])
        assert trial['robustness']['zero_cost_stress'] is (not promising)
        assert len({c['data_fingerprint'] for c in trial['robustness']['cells']})==2
        expected_calls = 8 if promising=='iterate_restart' else 4
        assert len(model.calls)==expected_calls
        if promising in {'simpler_parent','iterate_restart'}:
            assert entry['research_decision']['simplification']['verdict'] == 'PREFER_SIMPLER_PARENT'
            assert entry['research_decision']['verdict'] == 'REJECTED_DEVELOPMENT'
            assert not entry.get('frozen_candidate_id')
            assert entry['family_outcome'] == 'STOPPED_WITHOUT_ACCEPTANCE'
            director.tick()
            assert len(model.calls) == expected_calls and trial['reserved_runs'] == 20
            assert any(d['state']=='LOCKED_HOLDOUT' for d in ResearchRepository(director.database).get(entry['reference_project_id'])['datasets'])
            if promising=='iterate_restart':
                attempts = entry['structural_attempts']
                assert len(attempts)==2 and len({a['source_sha256'] for a in attempts})==2
                assert sum(runner.get(a['sandbox_id'])['reserved_runs'] for a in attempts)==40
                assert result['reserved']==started['reserved']
                prior_context = model.calls[4][1]
                assert prior_context['prior_structural_attempts'][0]['sandbox_id']==attempts[0]['sandbox_id']
                assert prior_context['development_search_history']['debt']['structural_author_requests']==1
                before_jobs=len(director.services.backtest_jobs.list())
                for _ in range(3):director.tick()
                assert len(model.calls)==8 and len(director.services.backtest_jobs.list())==before_jobs
                assert director.campaigns.get(campaign['id'])==result
        elif promising:
            from app.research_agent.structural_candidates import freeze
            from app.research_agent.candidates import Candidates
            frozen=next(c for c in Candidates(director.database).list(entry['reference_project_id']) if c['id']==entry['frozen_candidate_id'])
            assert entry['family_outcome']=='FROZEN_REQUIRES_VALIDATION'
            assert frozen['state']=='FROZEN_DEVELOPMENT' and not frozen['validation_granted']
            assert not frozen['execution_enabled']
            assert freeze(director.database,campaign['id'],entry['reference_project_id'],entry['sandbox_id'])==frozen
            assert any(d['state']=='LOCKED_HOLDOUT' for d in ResearchRepository(director.database).get(entry['reference_project_id'])['datasets'])
            from app.research_agent.validation import Validations
            with pytest.raises(ValueError,match='Frozen candidate required'):
                Validations(director.database).approve(entry['reference_project_id'],frozen['id'],'any',{})
            if promising!='automatic':director.tick()
            assert len([c for c in Candidates(director.database).list(entry['reference_project_id']) if c.get('kind')=='GENERATED_DEVELOPMENT'])==1
            project=ResearchRepository(director.database).get(entry['reference_project_id'])
            dataset=next(d for d in project['datasets'] if d['state']=='LOCKED_HOLDOUT')
            before_jobs=len(director.services.backtest_jobs.list())
            before_runs=len(backtest.runs.list())
            if promising=='automatic':
                director.tick()
                grant=Validations(director.database).list(project['id'])[0]
                assert grant['authorization']=='campaign_policy'
            else:grant=runner.approve_validation(project['id'],frozen['id'],dataset['id'],{'minimum_trades':1})
            runner.thread.join(timeout=90)
            assert not runner.thread.is_alive()
            validation=Validations(director.database).get(grant['id'])
            assert validation['status']=='COMPLETED',validation
            if promising=='automatic':
                director.tick()
                selection=director.campaigns.get(campaign['id'])['validation']
                assert selection['validation_id']==grant['id'] and selection['status']=='COMPLETED'
            assert validation['control_parity'] and validation['causality']['prefix_match']
            assert validation['provenance']['source_sha256']==frozen['snapshot']['source_sha256']
            assert validation['data_fingerprint']!=frozen['snapshot']['data_fingerprint']
            assert len(director.services.backtest_jobs.list())==before_jobs
            assert len(backtest.runs.list())==before_runs
            assert runner.approve_validation(project['id'],frozen['id'],dataset['id'],{'minimum_trades':1})['id']==grant['id']
            assert Candidates(director.database).list(project['id'])[-1]==frozen
            assert next(d for d in ResearchRepository(director.database).get(project['id'])['datasets'] if d['id']==dataset['id'])['state']=='INSPECTED_VALIDATION'
            from app.research_agent.decisions import Decisions
            from tests.test_research_decisions import request as decision_request
            assert validation['verdict']=='INSUFFICIENT_EVIDENCE'  # One winner has no observed R loss denominator.
            with pytest.raises(ValueError,match='passing validation'):
                Decisions(director.database).record(project['id'],frozen['id'],decision_request('ACCEPTED_FOR_RESEARCH'))
            rejected=Decisions(director.database).record(project['id'],frozen['id'],decision_request())
            assert rejected['decision']=='REJECTED' and not frozen['execution_enabled']
    finally:
        runner.close()
        if restarted:restarted.close()
