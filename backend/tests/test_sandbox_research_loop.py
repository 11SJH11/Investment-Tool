"""Real Docker continuation of the deterministic research/candidate fixture."""
import os
import json
from unittest.mock import Mock, patch
import pytest
from app.research_agent.quarantine import store
from app.research_agent.sandbox_runs import SandboxRuns, ACK
from app.research_agent.sandbox import Docker
from tests.test_research_trials import research
from tests.test_research_validation import frozen
from tests.test_backtest_jobs import wait_for

pytestmark=pytest.mark.skipif(os.environ.get('LEDGER_TEST_DOCKER')!='1',reason='Opt-in real Docker research-loop acceptance')

SOURCE='''from app.backtesting.strategies.base import Strategy, StrategySpec
from app.backtesting.models import EntrySignal
class Child(Strategy):
    spec=StrategySpec(key='research_child_loop',name='Mock model child',defaults={'enabled':False},timeframes=('1m',))
    def reset(self):self.done=False
    def on_bar(self,ctx):
        if self.params['enabled']:return None
        if not self.done and ctx.position is None:
            self.done=True
            close=float(ctx.current_bar['close'])
            return EntrySignal('long',stop_loss=close-50,take_profit=close+100,reason='hold_to_end')
'''


def setup(frozen,source=SOURCE):
    (db,repo,project,hypothesis,jobs,backtest),candidate=frozen
    original_prepare=backtest.prepare
    def prepare(payload,**kwargs):
        # This older fake service unconditionally calls the queue-only validator;
        # production BacktestService guards it by queue ownership fields.
        from app.research_agent.workflow import validate_submission
        def validate(database,data):
            if data.get('research_project_id'):validate_submission(database,data)
        with patch('tests.test_research_trials.validate_submission',validate):
            return original_prepare(payload,**kwargs)
    backtest.prepare=prepare
    # Model text remains inert until the explicit Docker approval. No model tools are executed.
    model=Mock(return_value=source)
    draft=store(db,project['id'],candidate['id'],dict(request_key='mock-model-child',registry_key='research_child_loop',source=model(),rationale='Mocked code proposal',acknowledgement='Store this source as an inert quarantined draft; no execution or activation'))
    runner=SandboxRuns(db,backtest)
    request=dict(control_parameters={'enabled':False},candidate_parameters={'enabled':True},timeout_seconds=60,acknowledgement=ACK)
    return runner,project,candidate,draft,request


def finish(runner,item):
    runner.thread.join(timeout=90)
    assert not runner.thread.is_alive()
    return runner.get(item['id'])


def test_mocked_llm_child_control_causality_results_and_immutable_parent(frozen):
    runner,project,candidate,draft,request=setup(frozen)
    parent=runner.backtest.runs.get(candidate['run_id'])
    from app.backtesting.strategies import strategy_registry
    registry_before=[s.key for s in strategy_registry.specs()]
    jobs=frozen[0][4];job_count=len(jobs.list())
    try:
        item=runner.approve(project['id'],candidate['id'],draft['id'],request)
        result=finish(runner,item)
        assert result['status']=='COMPLETED',result
        assert result['control_parity'] and result['causality']['prefix_match']
        assert result['summary']['n']==0
        assert result['provenance']['source_sha256']==draft['source_sha256']
        assert runner.backtest.runs.get(candidate['run_id'])==parent
        assert runner.approve(project['id'],candidate['id'],draft['id'],request)['id']==item['id']
        with pytest.raises(ValueError,match='immutable'):runner.approve(project['id'],candidate['id'],draft['id'],{**request,'candidate_parameters':{}})
        assert runner.database.path.exists()
        assert [s.key for s in strategy_registry.specs()]==registry_before
        assert len(jobs.list())==job_count
    finally:runner.close()


def test_control_failure_does_not_run_candidate(frozen):
    runner,project,candidate,draft,request=setup(frozen,SOURCE.replace("close-50","close-49"))
    try:
        result=finish(runner,runner.approve(project['id'],candidate['id'],draft['id'],request))
        assert result['status']=='FAILED' and result['error']=='GENERATED_CONTROL_MISMATCH'
        assert 'result' not in result and result['phase']=='CONTROL_PARITY'
    finally:runner.close()


def test_changed_data_rejected_before_generated_execution(frozen):
    runner,project,candidate,draft,request=setup(frozen)
    runner.backtest.changed=True
    try:
        result=finish(runner,runner.approve(project['id'],candidate['id'],draft['id'],request))
        assert result['status']=='FAILED' and result['error']=='DATA_FINGERPRINT_MISMATCH'
    finally:runner.close()


def test_restart_marks_active_attempt_interrupted_without_retry(frozen):
    runner,project,candidate,draft,request=setup(frozen)
    try:
        with runner.database.connect() as c:
            c.execute('INSERT INTO agent_sandbox_runs VALUES (?,?,?,?)',('orphan',project['id'],draft['id'],json.dumps({'id':'orphan','status':'RUNNING','reserved_runs':4})))
        runner.recover()
        assert runner.get('orphan')['status']=='INTERRUPTED'
        assert runner.thread is None
    finally:runner.close()


def test_nondeterministic_candidate_cannot_pass_prefix_gate(frozen):
    source=SOURCE.replace("if self.params['enabled']:return None", "if self.params['enabled']:\n            import os\n            return EntrySignal('long',-48,102,reason=os.urandom(12).hex())")
    runner,project,candidate,draft,request=setup(frozen,source)
    try:
        result=finish(runner,runner.approve(project['id'],candidate['id'],draft['id'],request))
        assert result['status']=='FAILED' and result['error']=='CAUSALITY_OR_DETERMINISM_MISMATCH'
        assert 'result' not in result
    finally:runner.close()


def test_budget_counts_sandbox_attempts_and_prevents_new_approval(frozen):
    runner,project,candidate,draft,request=setup(frozen)
    try:
        with runner.database.connect() as c:
            p=json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?',(project['id'],)).fetchone()[0])
            p['research_budget']['max_trial_runs']=4
            c.execute('UPDATE agent_projects SET document=? WHERE id=?',(json.dumps(p),project['id']))
        with pytest.raises(ValueError,match='budget'):runner.approve(project['id'],candidate['id'],draft['id'],request)
        assert runner.list(project['id'])==[]
    finally:runner.close()


def test_sandbox_api_consent_and_status(frozen):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from app.api.research_agent import router
    runner,project,candidate,draft,request=setup(frozen)
    app=FastAPI();app.include_router(router);app.state.services=SimpleNamespace(database=runner.database,research_sandbox=runner)
    base='/strategy-lab/research-agent/'+project['id']
    url=base+'/candidates/'+candidate['id']+'/code-drafts/'+draft['id']+'/sandbox'
    try:
        with TestClient(app) as client:
            assert client.post(url,json={}).status_code==422
            response=client.post(url,json=request);assert response.status_code==200,response.text
            result=finish(runner,response.json());assert result['status']=='COMPLETED',result
            assert client.get(base+'/sandbox-runs').json()['items'][0]['id']==result['id']
    finally:runner.close()
