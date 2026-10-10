from copy import deepcopy
import pytest
from app.research_agent.manager import choose,review
from tests.test_research_trials import research
from tests.test_research_validation import frozen


def state():return dict(decision=None,active=False,validation=None,checks={k:None for k in ('cost','regime','simplification')},runs_remaining=20)


@pytest.mark.parametrize('change,action',[
    ({'decision':'REJECTED'},'COMPLETE'),({'active':True},'WAIT'),({'runs_remaining':0},'STOP_BUDGET'),
    ({'validation':{'verdict':'INSUFFICIENT_EVIDENCE'}},'REVIEW_VALIDATION'),({},'PLAN_COST_CHECK')])
def test_manager_policy_is_conservative(change,action):
    e=state();e.update(change);assert choose(e)[0]==action


def test_manager_requires_each_check_then_explicit_validation_and_acceptance():
    e=state();e['checks']['cost']={'status':'COMPLETED'};assert choose(e)[0]=='PLAN_REGIME_CHECK'
    e['checks']['regime']={'status':'COMPLETED'};assert choose(e)[0]=='REVIEW_ABLATION_PROPOSALS'
    e['checks']['simplification']={'status':'COMPLETED'};assert choose(e)[0]=='REQUEST_VALIDATION_APPROVAL'
    e['runs_remaining']=1;assert choose(e)[0]=='STOP_BUDGET'
    e['validation']={'verdict':'VALIDATION_PASS'};assert choose(e)[0]=='REVIEW_ACCEPTANCE'
    e['checks']['cost']['status']='FAILED';assert choose(e)[0]=='REVIEW_CHECK_FAILURE'


def test_review_is_recorded_idempotently_without_calls_jobs_or_holdout_use(frozen):
    (db,repo,project,_,jobs,_),candidate=frozen
    before=len(jobs.list());datasets=deepcopy(repo.get(project['id'])['datasets'])
    result=review(db,project['id'],candidate['id'])
    assert result['action']=='PLAN_COST_CHECK' and result['minimum_new_runs']==2
    assert review(db,project['id'],candidate['id'])==result
    assert len(jobs.list())==before and repo.get(project['id'])['datasets']==datasets
    with db.connect() as c:assert c.execute("SELECT COUNT(*) FROM agent_events WHERE action='candidate_manager_review'").fetchone()[0]==1
