import json
from types import SimpleNamespace
import pytest
from tests.test_research_hypotheses import registered
from tests.test_research_committee import FakeModel
from app.research_agent.committee import Committee
from app.research_agent.spending import quote, limit_microusd, usage_cost


def priced(registered, budget):
    db,_,project,proposal=registered
    with db.connect() as c:
        row=c.execute('SELECT document FROM agent_projects WHERE id=?',(project['id'],)).fetchone();document=json.loads(row[0])
        document['research_budget']['max_llm_spend_usd']=budget
        c.execute('UPDATE agent_projects SET document=? WHERE id=?',(json.dumps(document),project['id']))
    pricing=quote(SimpleNamespace(research_llm_model='fixture',research_llm_input_usd_per_million=1,research_llm_output_usd_per_million=2,research_llm_max_output_tokens=1000))
    model=FakeModel(proposal);model.status=lambda:{'configured':True,'provider':'fixture','model':'fixture','pricing':pricing}
    return Committee(db,model),model,project['id']


def test_exact_reservation_enforces_budget_after_restart(registered):
    committee,model,pid=priced(registered,.306)
    review=committee.review(pid,'one')
    assert review['status']=='COMPLETED',review
    assert review['reserved_cost_microusd']==306000
    assert review['usage']['Researcher']['estimated_cost_microusd']==300
    assert committee.public(pid)['reserved_cost_usd']==.306
    with pytest.raises(ValueError,match='monetary budget'):Committee(committee.database,model).review(pid,'two')
    assert len(model.calls)==3
    assert committee.review(pid,'one')['id']==review['id'] and len(model.calls)==3


def test_failure_never_refunds_unknown_paid_calls(registered):
    committee,model,pid=priced(registered,.306);model.fault=lambda role:{'invalid':'response'}
    assert committee.review(pid,'bad')['status']=='FAILED'
    assert committee.public(pid)['reserved_cost_usd']==.306
    with pytest.raises(ValueError,match='monetary budget'):committee.review(pid,'again')
    assert len(model.calls)==1


def test_unpriced_or_zero_budget_fails_before_paid_call(registered):
    committee,model,pid=priced(registered,0)
    with pytest.raises(ValueError,match='monetary budget'):committee.review(pid,'zero')
    model.status=lambda:{'configured':True,'provider':'fixture','model':'fixture'}
    with pytest.raises(ValueError,match='pricing'):committee.review(pid,'unpriced')
    assert not model.calls


def test_quotes_are_explicit_and_decimal_rounding_is_conservative():
    assert quote(SimpleNamespace()) is None
    assert limit_microusd(.0000019)==1
    assert usage_cost({'input_tokens':1,'output_tokens':1},{'input_usd_per_million':.1,'output_usd_per_million':.1})==1
    assert usage_cost({}, {'input_usd_per_million':1,'output_usd_per_million':1}) is None


def test_changed_price_stops_remaining_roles(registered):
    committee,model,pid=priced(registered,10);generate=model.generate;original=model.status()
    def change(*args):
        result=generate(*args);model.status=lambda:{**original,'model':'other'};return result
    model.generate=change;result=committee.review(pid,'changed')
    assert result['status']=='FAILED' and result['error']=='model_or_pricing_changed'
    assert len(model.calls)==1


def test_usage_above_reservation_blocks_all_later_calls(registered):
    committee,model,pid=priced(registered,10);generate=model.generate
    def unexpected(*args):
        result,usage=generate(*args);usage['input_tokens']=100001;return result,usage
    model.generate=unexpected
    review=committee.review(pid,'unexpected')
    assert review['error']=='usage_exceeded_cost_reservation'
    with pytest.raises(ValueError,match='spending is blocked'):committee.review(pid,'later')
    assert len(model.calls)==1
