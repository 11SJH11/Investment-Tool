"""Immutable saved-run deployment drafts. No worker start or order authorization."""
from contextlib import closing
from datetime import datetime,timezone
import json
from uuid import uuid4
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from app.forward.deployments import digest,encoded
from app.forward.mt5_t01_runtime import SUPPORTED_KEYS
from app.storage.strategy_source_archive import export_run


class DeploymentDraft(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    request_key:str=Field(min_length=1,max_length=128)
    name:str=Field(min_length=1,max_length=100)
    run_id:int=Field(gt=0,strict=True)
    profile_id:str=Field(pattern=r'^[a-z][a-z0-9-]{0,59}$')
    broker_symbol:str=Field(min_length=1,max_length=100)
    strategy_key:Literal['gold_ifvg_v2_fvg_ratio_020','gold_ifvg_v2_skip_23et']='gold_ifvg_v2_fvg_ratio_020'
    mode:Literal['SHADOW','DEMO']='SHADOW'
    risk_percent:float=Field(default=.5,gt=0,le=5)
    max_daily_loss_percent:float=Field(default=2,gt=0,le=20)
    max_daily_loss_cash:float|None=Field(default=None,gt=0)
    max_positions:int=Field(default=1,ge=1,le=10,strict=True)
    max_trades_per_day:int=Field(default=1,ge=1,le=100,strict=True)
    max_gross_exposure:float=Field(gt=0)
    direction:Literal['long','short','both']|None=None


class MT5Deployments:
    def __init__(self,database,connections,registry=None):
        if registry is None:
            from app.backtesting.strategies import strategy_registry
            registry=strategy_registry
        self.database,self.connections,self.registry=database,connections,registry

    def preview(self,request):
        from app.brokers.mt5_execution_ledger import MT5ExecutionLedger
        MT5ExecutionLedger._manual_only()
        draft=DeploymentDraft.model_validate(request)
        status=self.connections.status(draft.profile_id)
        if status['provider']!='mt5' or status['environment']!='demo' or not status['configured'] or not status.get('account_key'):
            raise ValueError('An enabled, selected MT5 DEMO account is required')
        with self.registry.executing(),closing(self.database.connect()) as c:
            row=c.execute("SELECT config_json,json_extract(result_json,'$.strategy'),symbols,primary_timeframe FROM backtest_runs WHERE id=?",(draft.run_id,)).fetchone()
            if not row:raise ValueError('Saved backtest not found')
            config,strategy,symbols=json.loads(row[0]),json.loads(row[1] or '{}'),json.loads(row[2])
            key=strategy.get('key')
            if key!=draft.strategy_key:
                raise ValueError('Selected saved result does not use the requested deployment strategy')
            if key not in SUPPORTED_KEYS or config.get('strategy_key')!=key or row[3]!='1m' or len(symbols)!=1:
                raise ValueError('A single-symbol, 1m execution T01/T02 saved run is required')
            current=self.registry.provenance(key)
            if strategy.get('implementation')!=current:
                raise ValueError('Installed implementation differs from the saved run; deployment is blocked')
            archive=export_run(self.database,draft.run_id)
            params={'direction':'both',**config.get('strategy_params',{})}
            if set(params)!={'direction'} or params['direction'] not in {'long','short','both'}:
                raise ValueError('Saved parameters do not match the frozen Gold contract')
            if draft.direction is not None:params['direction']=draft.direction
            # Never silently remap a symbol by suffix/name resemblance.
            catalog=self.connections.symbol_catalog(draft.profile_id,search=draft.broker_symbol,limit=500)
            symbol=next((s for s in catalog.get('items',[]) if s['name']==draft.broker_symbol),None)
            if (not symbol or symbol.get('account_key')!=status['account_key'] or symbol.get('environment')!='demo'
                    or symbol.get('currency_base')!='XAU' or symbol.get('currency_profit')!='USD'
                    or symbols[0] not in {'XAUUSD',draft.broker_symbol}):
                raise ValueError('Discover an exact XAU/USD broker symbol for the selected DEMO account first')
            observation=self.connections.account_observations(draft.profile_id,history=False)
            snapshot=observation['snapshot']
            if not snapshot or snapshot['account_key']!=status['account_key'] or snapshot['environment']!='demo':
                raise ValueError('A recorded observation for this exact DEMO account is required')
            current_status=self.connections.status(draft.profile_id)
            if any(current_status.get(k)!=status.get(k) for k in ('provider','environment','configured','account_key')):
                raise ValueError('Selected account changed during deployment preparation; retry')
            definition=dict(version='mt5_deployment_v1',name=draft.name,mode=draft.mode,
                run_id=draft.run_id,profile_id=draft.profile_id,account_key=status['account_key'],environment='demo',
                currency=snapshot['account']['currency'],strategy_key=key,implementation=current,
                source_archive=archive['archive'],saved_config=config,saved_config_sha256=digest(config),
                parameters=params,broker_symbol=draft.broker_symbol,backtest_symbol=symbols[0],
                primary_timeframe='1m',signal_timeframe='15m',session_timezone='America/New_York',session=['20:00','00:00'],
                risk={k:getattr(draft,k) for k in ('risk_percent','max_daily_loss_percent','max_daily_loss_cash','max_positions','max_trades_per_day','max_gross_exposure')},
                daily_loss_boundary='UTC',external_positions_policy='block_if_risk_or_ownership_unverified')
            return dict(definition=definition,definition_sha256=digest(definition),execution_enabled=False,
                estimated_target_risk=snapshot['account']['equity']*draft.risk_percent/100,
                estimate_observed_at=snapshot['observed_at'],estimate_currency=snapshot['account']['currency'],
                blockers=['execution_gateway_not_accepted','timestamp_policy_unverified','account_coexistence_unverified','activation_not_authorized'],
                warning='Estimate uses recorded equity, not a fresh executable quote or margin approval. Draft creation does not start a worker or modify the saved run.')

    def create(self,request):
        draft=DeploymentDraft.model_validate(request)
        request_hash=digest(draft.model_dump())
        # Retrying an identical request returns its original immutable draft.
        with closing(self.database.connect()) as c:
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='mt5_algo_deployments'").fetchone():
                previous=c.execute('SELECT request_sha256,document FROM mt5_algo_deployments WHERE request_key=?',(draft.request_key,)).fetchone()
                if previous:
                    if previous[0]!=request_hash:raise ValueError('Request key belongs to different deployment settings')
                    return self._checked(previous[1])
        prepared=self.preview(draft.model_dump())
        item=dict(id=str(uuid4()),created_at=datetime.now(timezone.utc).isoformat(),state='DRAFT',**prepared)
        with closing(self.database.connect()) as c,c:
            c.execute('CREATE TABLE IF NOT EXISTS mt5_algo_deployments(id TEXT PRIMARY KEY,request_key TEXT UNIQUE NOT NULL,request_sha256 TEXT NOT NULL,document TEXT NOT NULL)')
            c.execute('INSERT OR IGNORE INTO mt5_algo_deployments VALUES(?,?,?,?)',(item['id'],draft.request_key,request_hash,encoded(item)))
            previous=c.execute('SELECT request_sha256,document FROM mt5_algo_deployments WHERE request_key=?',(draft.request_key,)).fetchone()
            if previous[0]!=request_hash:raise ValueError('Request key belongs to different deployment settings')
            return self._checked(previous[1])

    @staticmethod
    def _checked(document):
        value=json.loads(document)
        if digest(value['definition'])!=value['definition_sha256']:
            raise ValueError('Stored deployment definition integrity failed')
        return value

    def list(self):
        with closing(self.database.connect()) as c:
            if not c.execute("SELECT 1 FROM sqlite_master WHERE name='mt5_algo_deployments'").fetchone():return []
            return [self._checked(row[0]) for row in c.execute('SELECT document FROM mt5_algo_deployments ORDER BY rowid DESC LIMIT 500')]
