"""Explicit candidate cost reruns using the shared development trial coordinator."""
from typing import Literal
from pydantic import Field
from .hypotheses import Strict

COSTS = ('commission_per_order', 'spread_bps', 'slippage_bps')


class Scenario(Strict):
    name: str = Field(min_length=1, max_length=80)
    commission_per_order: float = Field(ge=0, le=10000)
    spread_bps: float = Field(ge=0, le=1000)
    slippage_bps: float = Field(ge=0, le=1000)


class CostApproval(Strict):
    scenarios: list[Scenario] = Field(min_length=1, max_length=6)
    rationale: str = Field(min_length=1, max_length=4000)
    acknowledgement: Literal['Run the frozen candidate control and declared development cost scenarios']


def scenarios(base, request):
    settings = [tuple(s[k] for k in COSTS) for s in request['scenarios']]
    original = tuple(float(base.get(k) or 0) for k in COSTS)
    if len(set(settings)) != len(settings) or original in settings:
        raise ValueError('Scenarios must differ from each other and the control')
    if any(any(v < b for v, b in zip(values, original)) for values in settings):
        raise ValueError('Cost stress cannot reduce frozen execution costs')
    return [{'name':s['name'], 'overrides':{k:s[k] for k in COSTS}} for s in request['scenarios']]


def approve(database, project_id, candidate_id, payload):
    from .candidate_checks import approve as approve_check
    request = CostApproval.model_validate(payload).model_dump()
    return approve_check(database, project_id, candidate_id, request, kind='cost', build_scenarios=scenarios)


def report(database, project_id, candidate_id):
    from .candidate_checks import report as check_report
    return check_report(database, project_id, candidate_id, kind='cost')
