import json
import pytest
from app.research_agent.committee import Committee, Researcher
from app.research_agent.llm import ModelFailure, strict_schema
from app.research_agent.model_diagnostics import validate_evidence, public_validation
from app.research_agent.market_preflight import validate_research_market
from app.research_agent.preparation_errors import preparation_failure
from tests.test_research_hypotheses import registered
from tests.test_research_committee import FakeModel


def test_actual_orb_xau_configuration_rejected_without_loading_history():
    with pytest.raises(ValueError, match='STRATEGY_INSTRUMENT_UNSUPPORTED') as failure:
        validate_research_market('opening_range_breakout_research_v1', ['XAUUSD'], '1m')
    assert preparation_failure(failure.value)['category']=='strategy_instrument_unsupported'
    validate_research_market('opening_range_breakout_research_v1', ['QQQ'], '1m')
    validate_research_market('vwap_trend_confirmation_quality_research_v5', ['XAUUSD'], '1m')


def test_evidence_schema_is_exact_and_does_not_mutate_global_model():
    schema=strict_schema(Researcher, {'evidence':{'summary':{},'breakdowns/session/NY':{}}})
    assert schema['properties']['evidence_refs']['items']['enum']==['breakdowns/session/NY','summary']
    assert 'enum' not in strict_schema(Researcher)['properties']['evidence_refs']['items']
    with pytest.raises(ModelFailure,match='missing_evidence_ids'):
        strict_schema(Researcher, {'evidence':{}})


def test_rejected_references_are_hashed_not_exposed():
    document={'id':'fixture','operation':{'role':'Researcher'}}
    with pytest.raises(ModelFailure):
        validate_evidence(document,['Bearer PRIVATE_SECRET /private/path'],{'summary':{'locked':'HOLDOUT'}})
    document['error']='unknown_evidence_reference'
    assert 'PRIVATE_SECRET' not in json.dumps(document)
    public=public_validation(document)
    assert public['details']=={'invalid_reference_count':1,'supplied_evidence_count':1}
    assert 'HOLDOUT' not in json.dumps(public)


def test_failed_review_retains_diagnostics_across_reload_without_retry(registered):
    db,_,project,proposal=registered
    def bad(role):
        result={key:proposal[key] for key in ('description','rationale','feature','expected_result','falsification','axes')}
        return dict(result,decision='PROPOSE',evidence_refs=['not-supplied'])
    model=FakeModel(proposal,bad)
    record=Committee(db,model).review(project['id'],'diagnostic')
    assert record['error']=='unknown_evidence_reference'
    assert record['validation_diagnostic']['details']['invalid_reference_count']==1
    assert Committee(db,model).review(project['id'],'diagnostic')==record and len(model.calls)==1
    assert not record['roles']


def test_legacy_failure_is_reported_without_fabricated_details():
    event=public_validation({'id':'legacy','error':'unknown_evidence_reference'})
    assert event['legacy_details_unavailable'] and event['details']=={}
    assert public_validation({'id':'other','error':'secret'}) is None
