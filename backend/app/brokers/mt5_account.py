"""Allowlisted current terminal facts for future risk checks, never order methods."""
from datetime import datetime, timezone
import math

from app.brokers.base import BrokerHistoryError


def read_snapshot(adapter):
    try:
        account,key=adapter._account()
        if key!=adapter.account_key:raise ValueError('account changed')
        positions=adapter._module.positions_get()
        orders=adapter._module.orders_get()
        if positions is None or orders is None or len(positions)>10000 or len(orders)>10000:
            raise ValueError('incomplete snapshot')
        def facts(row, fields):
            result={}
            for field in fields:
                value=getattr(row,field,None)
                if isinstance(value,str):
                    if field not in {'symbol','currency'} or len(value)>256:raise ValueError('unexpected text')
                elif isinstance(value,(int,float)) and not isinstance(value,bool):
                    if not math.isfinite(value):raise ValueError('invalid numeric fact')
                else:raise ValueError('missing fact')
                result[field]=value
            return result
        balance=facts(account,('balance','equity','margin','margin_free','currency'))
        position_rows=[facts(p,('ticket','identifier','symbol','type','volume','price_open','price_current','sl','tp','profit','swap','time_msc')) for p in positions]
        order_rows=[facts(o,('ticket','symbol','type','state','volume_initial','volume_current','price_open','sl','tp','time_setup_msc')) for o in orders]
        if len({p['ticket'] for p in position_rows})!=len(position_rows) or len({o['ticket'] for o in order_rows})!=len(order_rows):
            raise ValueError('duplicate identity')
        if adapter._account()[1]!=key:raise ValueError('account changed')
        return dict(provider='mt5',account_key=key,environment=adapter.environment,
            observed_at=datetime.now(timezone.utc).isoformat(),account=balance,
            positions=position_rows,pending_orders=order_rows,execution_enabled=False,
            snapshot_atomic=False,
            warning='Sequential read-only observations; facts can change between calls. Not an execution approval.')
    except Exception:
        raise BrokerHistoryError('MT5 account snapshot unavailable or changed; previous data must not be treated as closed',category='connection') from None
