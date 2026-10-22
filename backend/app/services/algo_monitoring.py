"""Read-only operational overview. Never initializes a terminal or execution ledger.

Prepared MT5 policies are not deployments; manual broker trades are not attributed
to them. Shadow equity is simulation evidence, never a broker account balance.
"""
from datetime import datetime,timezone
import json


def report(services):
    accounts=[];items=[];warnings=[]
    connections=getattr(services,'broker_connections',None)
    if connections:
        for row in connections.statuses()['items']:
            if row.get('provider')!='mt5':continue
            accounts.append({k:row.get(k) for k in ('profile_id','provider','environment','configured','status','account_key','last_success_at','error_category')})
    with services.database.connect() as c:
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'mt5_execution_policies' in tables:
            rows=c.execute('SELECT document FROM mt5_execution_policies ORDER BY rowid DESC LIMIT 501').fetchall()
            if len(rows)>500:warnings.append('Only the latest 500 MT5 preparations are shown.')
            for raw in rows[:500]:
                saved=json.loads(raw[0]);policy=saved['policy']
                counts={}
                if 'mt5_execution_intents' in tables:
                    counts={r[0]:r[1] for r in c.execute("SELECT json_extract(document,'$.state'),COUNT(*) FROM mt5_execution_intents WHERE policy_id=? GROUP BY json_extract(document,'$.state')",(saved['id'],))}
                items.append(dict(id=saved['id'],name=policy['strategy_key'],strategy_key=policy['strategy_key'],
                    mode='MT5_PREPARATION',environment=policy['environment'],symbol=', '.join(policy['symbols']),
                    account_key=policy['account_key'],currency=policy['currency'],
                    status='NOT_DEPLOYED',persisted_status=saved['status'],execution_enabled=False,
                    source_hash=policy['strategy_source_hash'],created_at=saved.get('created_at'),
                    last_evaluation_at=None,metrics=None,position=None,trades=[],risk=policy,intent_counts=counts,
                    limitation='Saved risk policy only. No MT5 strategy worker or trading permission is established.'))
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
    return dict(observed_at=datetime.now(timezone.utc).isoformat(),items=items,accounts=accounts,warnings=warnings,
        mt5_execution_enabled=False,broker_totals=None,
        limitation='Monitoring foundation: broker connectivity is last sync evidence, not a current terminal probe. No account balances are inferred or pooled. Paper controls remain in Forward validation; T01 deployment/execution integration is not complete.')
