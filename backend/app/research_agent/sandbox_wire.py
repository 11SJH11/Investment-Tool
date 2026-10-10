"""Bounded JSON signals: no executable objects cross the container boundary."""
from dataclasses import asdict, fields
from datetime import datetime
import json
import math
from app.backtesting.models import EntrySignal, ExitSignal, ManagePositionSignal

MAX_MESSAGE = 8 * 1024 * 1024
MAX_REPLY = 64 * 1024
TYPES = {c.__name__: c for c in (EntrySignal, ExitSignal, ManagePositionSignal)}


def encode(value):
    return json.dumps(value, allow_nan=False, separators=(',', ':'), default=lambda v: v.isoformat()).encode() + b'\n'


def decode(raw, limit=MAX_REPLY):
    if len(raw) > limit: raise ValueError('Sandbox message limit exceeded')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    def invalid(_): raise ValueError('Non-finite JSON value')
    result = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    def walk(value, depth=0):
        if depth > 20: raise ValueError('Sandbox JSON nesting limit')
        if isinstance(value, float) and not math.isfinite(value): raise ValueError('Non-finite number')
        if isinstance(value, (dict, list)):
            for child in (value.values() if isinstance(value, dict) else value): walk(child, depth+1)
    walk(result)
    return result


def signal_from_json(value):
    if value is None: return None
    if not isinstance(value, dict) or set(value) != {'type', 'value'} or value['type'] not in TYPES:
        raise ValueError('Invalid sandbox signal envelope')
    cls = TYPES[value['type']]; data = value['value']
    if not isinstance(data, dict) or set(data) - {f.name for f in fields(cls)}:
        raise ValueError('Unknown sandbox signal field')
    for name, val in data.items():
        if name == 'metadata':
            if not isinstance(val, dict): raise ValueError('Invalid signal metadata')
        elif name in {'reason', 'rejection_reason'}:
            if val is not None and (not isinstance(val, str) or len(val)>2000): raise ValueError('Invalid reason')
        elif name == 'direction':
            if val not in {'long', 'short'}: raise ValueError('Invalid direction')
        elif name == 'order_type':
            if val not in {'market', 'limit'}: raise ValueError('Invalid order type')
        elif name == 'fill_time_filters_only':
            if type(val) is not bool: raise ValueError('Invalid signal flag')
        elif name == 'expires_at':
            if val is not None:
                data[name] = datetime.fromisoformat(val)
                if data[name].utcoffset() is None: raise ValueError('Expiry must be timezone aware')
        elif val is not None:
            if type(val) not in {int,float} or not math.isfinite(val): raise ValueError('Invalid numeric signal field')
            if name == 'max_wait_bars' and (type(val) is not int or val<1): raise ValueError('Invalid wait limit')
    return cls(**data)


def signal_to_json(signal):
    if signal is None: return None
    if type(signal).__name__ not in TYPES or type(signal) is not TYPES[type(signal).__name__]:
        raise ValueError('Strategy returned an incompatible signal')
    return {'type': type(signal).__name__, 'value': asdict(signal)}
