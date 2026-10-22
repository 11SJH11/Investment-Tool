"""Allowlisted persisted operation metadata. Never load evidence, source or results."""
from datetime import datetime, timezone
import json


def _seconds(start, end):
    try:
        a,b=(datetime.fromisoformat(v.replace('Z','+00:00')) for v in (start,end))
        if a.tzinfo is None or b.tzinfo is None:
            return None
        return max(0.,(b-a).total_seconds())
    except (AttributeError,TypeError,ValueError):
        return None


def operations(database,campaign,*,now=None):
    stamp=(now or datetime.now(timezone.utc)).isoformat()
    projects={e[k]:e['family_id'] for e in campaign.get('execution',{}).get('entries',[])
              for k in ('project_id','reference_project_id') if e.get(k)}
    rows=[]
    with database.connect() as c:
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'agent_reviews' in tables:
            for pid,family in projects.items():
                for raw in c.execute('SELECT document FROM agent_reviews WHERE project_id=? ORDER BY rowid',(pid,)):
                    record=json.loads(raw[0]);op=record.get('operation') or {}
                    usage=record.get('usage') or {}
                    metering=[{k:v.get(k) for k in ('input_tokens','output_tokens','estimated_cost_microusd')}
                              for v in usage.values()]
                    costs=[m['estimated_cost_microusd'] for m in metering if type(m['estimated_cost_microusd']) is int and m['estimated_cost_microusd']>=0]
                    rows.append(dict(id=record['id'],family_id=family,kind=record.get('kind','COMMITTEE'),
                        status=record['status'],created_at=record.get('created_at'),finished_at=record.get('finished_at'),
                        updated_at=record.get('updated_at'),deadline=record.get('deadline'),
                        operation={k:op.get(k) for k in ('kind','role','status','started_at','finished_at')},
                        elapsed_seconds=_seconds(op.get('started_at'),op.get('finished_at') or record.get('finished_at') or stamp),
                        reserved_calls=record.get('reserved_calls'),reserved_cost_microusd=record.get('reserved_cost_microusd'),
                        returned_usage_calls=len(usage),estimated_reported_cost_microusd=sum(costs) if costs else None,
                        unpriced_returned_calls=len(usage)-len(costs),
                        deadline_elapsed=record['status']=='RUNNING' and _seconds(record.get('deadline'),stamp) not in (None,0.)))
    return dict(model_operations=rows,observed_at=stamp,
        limitation='Recorded calls only. Returned usage is not an invoice; unknown/failed calls remain reserved. Operation timestamps are not a live worker heartbeat. No automatic retry or cancellation.')
