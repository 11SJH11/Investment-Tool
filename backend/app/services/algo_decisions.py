"""Bounded read-only projection of persisted diagnostics, never trade attribution."""
import json
import math
import re

from app.forward.deployments import digest


def decision_page(database, *, stream_id, before=None, limit=50):
    if not isinstance(stream_id, str) or not re.fullmatch('[a-f0-9]{64}', stream_id):
        raise ValueError('Invalid diagnostic stream')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Invalid page size')
    if before is not None and (type(before) is not int or before <= 0):
        raise ValueError('Invalid decision cursor')
    with database.connect() as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mt5_t01_decisions'").fetchone():
            return dict(items=[], next_before=None)
        rows = c.execute('''SELECT sequence,document,sha256 FROM mt5_t01_decisions
            WHERE deployment_id=?''' + (' AND sequence<?' if before is not None else '') +
            ' ORDER BY sequence DESC LIMIT ?',
            (stream_id, *((before,) if before is not None else ()), limit+1)).fetchall()
    items = []
    for sequence, raw, checksum in rows[:limit]:
        row = dict(id=f'{stream_id}:{sequence}', sequence=sequence,
                   integrity='invalid', decision_kind='Unavailable', execution_enabled=False)
        try:
            saved = json.loads(raw)
            if digest(saved) != checksum or not isinstance(saved, dict):
                raise ValueError('Invalid evidence')
            result = saved.get('result')
            if result is not None and (not isinstance(result, dict) or result.get('kind') not in ('entry','manage','exit')):
                raise ValueError('Invalid decision')
            signal = result.get('signal', {}) if result else {}
            if not isinstance(signal, dict):
                raise ValueError('Invalid signal')
            # Never return raw provider observations, position metadata or source.
            projected = dict(integrity='checksum_verified', decision_kind=result['kind'] if result else 'no_signal')
            for field in ('decision_at','observed_at','not_before'):
                value = saved.get(field)
                if isinstance(value, str) and len(value) <= 64:
                    projected[field] = value
            if signal.get('direction') in ('long','short'):
                projected['direction'] = signal['direction']
            for field in ('stop_loss','target_r','take_profit','new_stop_loss'):
                value = signal.get(field)
                if type(value) in (float,int) and math.isfinite(value):
                    projected[field] = value
            row.update(projected)
        except (ValueError, TypeError, OverflowError):
            pass  # Keep the corrupt row visible, without presenting its contents.
        items.append(row)
    return dict(items=items, next_before=rows[limit-1][0] if len(rows)>limit else None)
