"""Restricted JSON protocol shared with the standalone Wine service (stdlib only)."""
from datetime import datetime, timezone
import math

MAX_REQUEST=16384
MAX_RESPONSE=32*1024*1024
MAX_ROWS=100000
METHODS={'account_info','terminal_info','symbols_get','symbol_info','symbol_info_tick',
         'symbol_select','positions_get','orders_get','history_deals_get','history_orders_get',
         'copy_rates_range','copy_ticks_range','tick_diagnostics'}
CONSTANTS=('ACCOUNT_TRADE_MODE_DEMO','ACCOUNT_TRADE_MODE_REAL','ORDER_TYPE_BUY','ORDER_TYPE_SELL',
 'DEAL_REASON_EXPERT','COPY_TICKS_ALL','TIMEFRAME_M1','TIMEFRAME_M5','TIMEFRAME_M15','TIMEFRAME_M30',
 'TIMEFRAME_H1','TIMEFRAME_H4','TIMEFRAME_D1')


class ProtocolError(ValueError):pass


def validate(method,args,kwargs):
    if method not in METHODS or not isinstance(args,list) or not isinstance(kwargs,dict):raise ProtocolError('unsupported')
    def symbol(value):
        if not isinstance(value,str) or not 1<=len(value)<=256 or any(ord(c)<32 for c in value):raise ProtocolError('invalid_request')
    def interval(a,b,days):
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in (a,b)) or not 0<b-a<=days*86400:raise ProtocolError('invalid_interval')
        return datetime.fromtimestamp(a,timezone.utc),datetime.fromtimestamp(b,timezone.utc)
    if method in {'account_info','terminal_info','symbols_get','positions_get','orders_get'}:
        if args or kwargs:raise ProtocolError('invalid_request')
    elif method in {'symbol_info','symbol_info_tick','tick_diagnostics','symbol_select'}:
        if kwargs or len(args)!=(2 if method=='symbol_select' else 1):raise ProtocolError('invalid_request')
        symbol(args[0])
        if method=='symbol_select' and args[1] is not True:raise ProtocolError('unsupported')
    elif method.startswith('history_'):
        if kwargs:
            if args or set(kwargs)!={'position'} or type(kwargs['position']) is not int or kwargs['position']<=0:raise ProtocolError('invalid_request')
        elif len(args)==2:args=list(interval(*args,days=36500))
        else:raise ProtocolError('invalid_request')
    else:
        if kwargs or len(args)!=4:raise ProtocolError('invalid_request')
        symbol(args[0])
        if method=='copy_rates_range':
            if args[1] not in ('TIMEFRAME_M1','TIMEFRAME_M5','TIMEFRAME_M15','TIMEFRAME_M30','TIMEFRAME_H1','TIMEFRAME_H4','TIMEFRAME_D1'):raise ProtocolError('unsupported')
            args=[args[0],args[1],*interval(args[2],args[3],7)]
        else:
            if args[3]!='COPY_TICKS_ALL':raise ProtocolError('unsupported')
            args=[args[0],*interval(args[1],args[2],1),args[3]]
    return args,kwargs


def encode(value,depth=0):
    if depth>8:raise ProtocolError('response_limit')
    if value is None or type(value) in (str,int,bool):return value
    if type(value) is float:
        if not math.isfinite(value):raise ProtocolError('invalid_response')
        return value
    if hasattr(value,'_asdict'):return {'record':encode(value._asdict(),depth+1)}
    if hasattr(value,'dtype') and value.dtype.names:
        if value.ndim!=1 or len(value)>MAX_ROWS:raise ProtocolError('response_limit')
        return [encode({n:row[n].item() for n in value.dtype.names},depth+1) for row in value]
    if isinstance(value,dict):return {k:encode(v,depth+1) for k,v in value.items() if k not in {'password','comment','external_id'}}
    if isinstance(value,(tuple,list)):
        if len(value)>MAX_ROWS:raise ProtocolError('response_limit')
        return [encode(v,depth+1) for v in value]
    raise ProtocolError('invalid_response')
