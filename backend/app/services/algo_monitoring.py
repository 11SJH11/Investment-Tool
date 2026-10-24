"""Read-only operational overview. Never initializes a terminal or execution ledger.

Prepared MT5 policies are not deployments; manual broker trades are not attributed
to them. Shadow equity is simulation evidence, never a broker account balance.
"""
from datetime import datetime,timezone
import json
from app.services.algo_safeguards import safeguards


def recovery_page(database,*,policy_id=None,before=None,limit=50):
    if type(limit) is not int or not 1<=limit<=100:raise ValueError('Invalid page size')
    if before is not None and (type(before) is not int or before<=0):raise ValueError('Invalid recovery cursor')
    if policy_id is not None and (not isinstance(policy_id,str) or not 1<=len(policy_id)<=128):raise ValueError('Invalid policy identity')
    with database.connect() as c:
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'mt5_execution_reconciliations','mt5_execution_intents'}<=tables:return dict(items=[],next_before=None)
        conditions=[];params=[]
        if policy_id is not None:conditions.append('i.policy_id=?');params.append(policy_id)
        if before is not None:conditions.append('r.rowid<?');params.append(before)
        where=' WHERE '+' AND '.join(conditions) if conditions else ''
        rows=c.execute('SELECT r.rowid,r.document,i.policy_id FROM mt5_execution_reconciliations r JOIN mt5_execution_intents i ON i.id=r.intent_id'+where+' ORDER BY r.rowid DESC LIMIT ?',(*params,limit+1)).fetchall()
        items=[]
        for raw in rows[:limit]:
            saved=json.loads(raw[1]);decision=saved.get('decision') or {}
            items.append(dict(id=saved['id'],policy_id=raw[2],intent_id=saved['intent_id'],
                observed_at_ms=saved.get('observed_at_ms'),state=decision.get('state','UNRESOLVED'),
                complete=saved.get('complete') is True,identity_basis=saved.get('identity_basis','unverified'),
                filled_lots=decision.get('filled_lots'),remaining_lots=decision.get('remaining_lots'),
                execution_count=saved.get('execution_count'),execution_enabled=False,attribution_verified=False))
        return dict(items=items,next_before=rows[limit-1][0] if len(rows)>limit else None)


def report(services):
    accounts=[];items=[];warnings=[];recovery=[]
    connections=getattr(services,'broker_connections',None)
    if connections:
        for row in connections.statuses()['items']:
            if row.get('provider')!='mt5':continue
            accounts.append({k:row.get(k) for k in ('profile_id','provider','environment','configured','status','account_key','last_success_at','error_category')})
    with services.database.connect() as c:
        c.execute('BEGIN')
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'mt5_execution_policies' in tables:
            rows=c.execute('SELECT document FROM mt5_execution_policies ORDER BY rowid DESC LIMIT 501').fetchall()
            if len(rows)>500:warnings.append('Only the latest 500 MT5 preparations are shown.')
            policies=[json.loads(raw[0]) for raw in rows[:500]]
            evidence=safeguards(c,tables,policies)
            for saved in policies:
                policy=saved['policy']
                counts={}
                if 'mt5_execution_intents' in tables:
                    counts={r[0]:r[1] for r in c.execute("SELECT json_extract(document,'$.state'),COUNT(*) FROM mt5_execution_intents WHERE policy_id=? GROUP BY json_extract(document,'$.state')",(saved['id'],))}
                items.append(dict(id=saved['id'],name=policy['strategy_key'],strategy_key=policy['strategy_key'],
                    mode='MT5_PREPARATION',environment=policy['environment'],symbol=', '.join(policy['symbols']),
                    account_key=policy['account_key'],currency=policy['currency'],
                    status='NOT_DEPLOYED',persisted_status=saved['status'],execution_enabled=False,
                    source_hash=policy['strategy_source_hash'],created_at=saved.get('created_at'),
                    last_evaluation_at=None,metrics=None,position=None,trades=[],risk=policy,intent_counts=counts,safeguards=evidence[saved['id']],
                    limitation='Saved risk policy only. No MT5 strategy worker or trading permission is established.'))
    recovery=recovery_page(services.database,limit=100)['items']
    forward=getattr(services,'forward',None)
    if forward:
        thread=getattr(forward,'thread',None)
        alive=bool(thread and thread.is_alive())
        for experiment in forward.report()['items']:
            for row in experiment['deployments']:
                state,definition=row['state'],row['definition']
                items.append(dict(id=row['id'],name=row['name'],strategy_key=definition['strategy_key'],
                    mode='SHADOW',environment='simulation',symbol=definition['symbol'],account_key=None,currency='USD',
                    status=('WORKER_UNAVAILABLE' if not alive else 'AWAITING_FRESH_EVALUATION') if state['status']=='ACTIVE' else state['status'],
                    persisted_status=state['status'],execution_enabled=False,source_hash=row['definition_sha256'],
                    created_at=state.get('started_at'),last_evaluation_at=state.get('last_evaluated_decision_at'),
                    metrics=row.get('metrics'),position=state.get('position'),trades=state.get('trade_history',[])[-100:],
                    equity=state.get('equity'),risk=definition['engine'],intent_counts={},
                    limitation='Independent simulated account. Active configuration alone does not prove fresh evaluation.'))
    diagnostic_service=getattr(services,'mt5_diagnostics',None)
    diagnostic_workers=diagnostic_service.report()['items'] if diagnostic_service else []
    return dict(observed_at=datetime.now(timezone.utc).isoformat(),items=items,accounts=accounts,warnings=warnings,recovery_observations=recovery,diagnostic_workers=diagnostic_workers,
        mt5_execution_enabled=False,broker_totals=None,
        limitation='Monitoring foundation: broker connectivity is last sync evidence, not a current terminal probe. No account balances are inferred or pooled. Paper controls remain in Forward validation; T01 deployment/execution integration is not complete.')
