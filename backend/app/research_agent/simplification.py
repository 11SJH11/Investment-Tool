"""User-declared single-rule ablations; no generated code or inferred off semantics."""
from copy import deepcopy
from typing import Annotated, Literal
from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr
from app.backtesting.strategies import strategy_registry
from app.services.research_experiments import preview
from .hypotheses import Strict
from . import candidate_checks


class Ablation(Strict):
    name: str = Field(min_length=1, max_length=80)
    parameter: str = Field(min_length=1, max_length=120)
    off_value: StrictBool | StrictInt | StrictFloat | Annotated[StrictStr, Field(max_length=120)]
    rule_removed: str = Field(min_length=1, max_length=2000)


class SimplificationApproval(Strict):
    scenarios: list[Ablation] = Field(min_length=1, max_length=6)
    rationale: str = Field(min_length=1, max_length=4000)
    acknowledgement: Literal['Run one declared rule ablation at a time on development data; off semantics are my responsibility']


def scenarios(base, request):
    spec = next((s for s in strategy_registry.specs() if s.key == base['strategy_key']), None)
    if spec is None:raise ValueError('Frozen strategy is unavailable')
    parameters = {p.key:p for p in (*spec.parameters, *spec.research_parameters)}
    current = {**spec.defaults, **{p.key:p.default for p in spec.research_parameters}, **base.get('strategy_params', {})}
    if len({s['parameter'] for s in request['scenarios']}) != len(request['scenarios']):
        raise ValueError('Test each rule once; no parameter sweep or combined ablation')
    result = []
    for item in request['scenarios']:
        key = item['parameter']; value = item['off_value']; parameter = parameters.get(key)
        if parameter is None:raise ValueError('Unknown declared strategy parameter')
        if parameter.kind in {'int','float'}:
            if type(value) not in {int,float}:raise ValueError('Numeric off value required')
            # Reuse canonical research parameter bounds, step and constructor validation.
            plan = preview(base, [dict(parameter=key, mode='explicit', values=[value])])
            value = plan['cells'][0][0]
        elif parameter.kind == 'bool':
            if type(value) is not bool:raise ValueError('Boolean off value required')
        elif parameter.kind == 'choice':
            if type(value) is not str or value not in parameter.choices:raise ValueError('Declared choice off value required')
        else:raise ValueError('Only declared numeric, boolean and choice parameters support ablations')
        if key not in current:raise ValueError('Frozen effective parameter value is unavailable')
        if current[key] == value:raise ValueError('Ablation must change the frozen parameter value')
        params = {**deepcopy(base.get('strategy_params', {})), key:value}
        strategy_registry.create(spec.key, **params)
        result.append({'name':item['name'], 'overrides':{'strategy_params':params}})
    return result


def approve(database, project_id, candidate_id, payload):
    request = SimplificationApproval.model_validate(payload).model_dump()
    return candidate_checks.approve(database, project_id, candidate_id, request, kind='simplification', build_scenarios=scenarios)


def report(database, project_id, candidate_id):
    return candidate_checks.report(database, project_id, candidate_id, kind='simplification')



def suggestions(database,project_id,candidate_id):
    """Deterministic proposals from declared parameter contracts, never results or guessed thresholds."""
    import re
    from .candidates import Candidates
    from .trials import check_source
    from .analysis import digest
    candidate=next((c for c in Candidates(database).list(project_id) if c['id']==candidate_id),None)
    if not candidate or digest(candidate['snapshot'])!=candidate['snapshot_hash']:raise ValueError('Valid frozen candidate required')
    check_source(candidate['snapshot']['hypothesis'])
    base=candidate['snapshot']['configuration']
    spec=next(s for s in strategy_registry.specs() if s.key==base['strategy_key'])
    current={**spec.defaults,**{p.key:p.default for p in spec.research_parameters},**base.get('strategy_params',{})}
    proposals=[]
    for p in sorted((*spec.parameters,*spec.research_parameters),key=lambda p:p.key):
        off=None;basis=None
        if p.kind=='bool' and current.get(p.key) is True:
            off=False;basis='Boolean toggle-off proposal; disabling the rule is not inferred from its name.'
        elif p.kind in {'int','float'} and re.search(r'(?<![\w.])0\s+disables?\b',p.help,re.I):
            off=0;basis='Declared parameter help: '+p.help
        if off is None or current.get(p.key)==off:continue
        proposal={'name':'Disable '+p.key,'parameter':p.key,'off_value':off,'rule_removed':basis+' User must verify the actual rule removed before approval.'}
        try:scenarios(base,{'scenarios':[proposal]})
        except ValueError:continue
        proposals.append(proposal)
    return {'candidate_hash':candidate['snapshot_hash'],'scenarios':proposals[:6],'omitted':max(0,len(proposals)-6),
            'rationale':'Independent single-rule ablations suggested from parameter declarations, not performance. Verify each off value and explanation.',
            'limitation':'Proposals only. Boolean false need not mean a simpler strategy. Numeric zero is proposed only when help explicitly says 0 disables. No inferred values for other parameters; no execution or acceptance.'}
