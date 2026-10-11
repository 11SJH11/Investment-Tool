"""One durable launch authorization; the Director owns preparation and execution."""
import json
from typing import Literal

from pydantic import Field

from .analysis import digest
from .campaigns import CampaignRequest, Campaigns
from .hypotheses import Strict

CONSENT='Authorize this bounded campaign, provider preparation and the selected model/code permissions'


class Launch(Strict):
    campaign: CampaignRequest
    engine: dict
    numeric_cycles: int = Field(default=0,ge=0,le=10,strict=True)
    structural: bool = False
    history: Literal['cached','provider'] = 'cached'
    lookback_days: int = Field(default=1460,ge=1,le=3650,strict=True)
    consent: Literal['Authorize this bounded campaign, provider preparation and the selected model/code permissions']


ENGINE_FIELDS={'starting_balance','sizing_mode','risk_value','commission_per_order','spread_bps','slippage_bps',
               'max_leverage','strategy_params','session'}


def launch(services,payload):
    from app.api.strategy_lab import BacktestRequest
    request=Launch.model_validate(payload).model_dump()
    config=request['engine']
    if set(config)-ENGINE_FIELDS:
        raise ValueError('Campaign engine settings include unsupported fields')
    required={'starting_balance','risk_value','commission_per_order','spread_bps','slippage_bps','max_leverage'}
    if not required<=set(config):
        raise ValueError('Explicit account, risk and execution costs are required')
    import math
    if any(type(config[k]) not in (int,float) or not math.isfinite(config[k]) or config[k]<0 for k in required):
        raise ValueError('Account, risk and cost settings must be finite and nonnegative')
    if any(config[k]<=0 for k in ('starting_balance','risk_value','max_leverage')):
        raise ValueError('Balance, risk and leverage must be positive')
    if config.get('sizing_mode','risk_pct')!='risk_pct' or config.get('session','regular')!='regular':
        raise ValueError('Campaign launch currently uses risk-percent sizing and regular sessions')
    # Validate types with the canonical contract, without executing or choosing dates.
    BacktestRequest.model_validate({**config,'strategy_key':'validation_only','symbols':['QQQ'],
                                   'primary_timeframe':'1m','start_date':'2000-01-01','end_date':'2000-01-02'})
    if request['campaign']['mode']=='RESEARCH_IDEA':
        raise ValueError('Novel strategy synthesis is not supported yet; select a registered strategy family')
    policy=request['campaign']['policy']
    if (request['numeric_cycles'] or request['structural']) and not policy['send_development_summaries']:
        raise ValueError('Model evidence consent is required')
    if request['structural'] and not policy['code_generation']:
        raise ValueError('Code-generation consent is required')
    if request['campaign']['mode']=='FIND_STRATEGIES' and config.get('strategy_params'):
        raise ValueError('Discovery uses each strategy default; strategy-specific overrides require Improve strategy')
    if request['numeric_cycles'] or request['structural']:
        worker=getattr(services,'research_loop',None)
        status=worker.committee.model.status() if worker else {}
        if not status.get('configured') or not status.get('pricing'):
            raise ValueError('Configured, priced model required before launch')
    if request['structural']:
        runner=getattr(services,'research_sandbox',None)
        if not runner or not getattr(services,'research_author',None):
            raise ValueError('Author and Docker services are unavailable')
        runner.docker.image()
    campaigns=Campaigns(services.database)
    campaign=campaigns.create(request['campaign'])
    execution={k:v for k,v in request.items() if k not in {'campaign','consent'}}
    with services.database.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        current=campaigns._get(c,campaign['id'])
        if current.get('launch'):
            if current['launch']['hash']!=digest(execution):
                raise ValueError('Launch authorization is immutable')
            return current
        if current['status']!='DRAFT':
            raise ValueError('Campaign has already been prepared')
        current['launch']={'hash':digest(execution),'configuration':execution}
        campaigns._save(c,current)
        campaigns._event(c,current['id'],'LAUNCH_AUTHORIZED',{'hash':digest(execution)})
    services.research_director.wake.set()
    return current


def advance(director,item):
    request=item['launch']['configuration']
    if digest(request)!=item['launch']['hash']:
        raise ValueError('Launch authorization integrity failed')
    if item['status']=='DRAFT':
        if request['history']=='provider':
            from .preparation import start
            start(director.services,item['id'],request['lookback_days'])
        else:
            from .discovery import prepare
            prepare(director.services,item['id'])
        return
    from .campaign_projects import provision
    links=provision(director.database,item['id'])
    director.start_baselines(item['id'],{p['project_id']:request['engine'] for p in links},
                             numeric_cycles=request['numeric_cycles'],structural=request['structural'])
