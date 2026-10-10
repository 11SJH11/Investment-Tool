from dataclasses import replace
from app.backtesting.strategies import strategy_registry
from app.backtesting.strategies.base import ParameterSpec
from app.research_agent.simplification import suggestions
from tests.test_research_trials import research
from tests.test_research_validation import frozen


def test_suggestions_are_contract_based_bounded_and_never_enqueue(frozen,monkeypatch):
    (db,_,project,_,jobs,_),candidate=frozen
    cls=strategy_registry._items[project['strategy_key']]
    declared=(ParameterSpec('guard','Guard','bool',True),ParameterSpec('distance','Distance','float',25,0,50,1,help='0 disables this filter.'),ParameterSpec('risk','Risk','float',1,0,5,1),ParameterSpec('negated','Negated','float',1,0,5,1,help='10 disables this filter.'),ParameterSpec('already_off','Already off','bool',False))
    monkeypatch.setattr(cls,'spec',replace(cls.spec,parameters=(*cls.spec.parameters,*declared),defaults={**cls.spec.defaults,**{p.key:p.default for p in declared}}))
    count=len(jobs.list())
    result=suggestions(db,project['id'],candidate['id'])
    assert [p['parameter'] for p in result['scenarios']]==['distance','guard']
    assert [p['off_value'] for p in result['scenarios']]==[0,False]
    assert len(jobs.list())==count
    assert result['candidate_hash']==candidate['snapshot_hash']
    assert result==suggestions(db,project['id'],candidate['id'])


def test_no_numeric_off_value_is_guessed(frozen):
    (db,_,project,_,_,_),candidate=frozen
    assert suggestions(db,project['id'],candidate['id'])['scenarios']==[]
