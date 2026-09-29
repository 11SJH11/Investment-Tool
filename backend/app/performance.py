"""Request-local, credential-free timings. Nested durations are inclusive."""
from contextvars import ContextVar
from contextlib import contextmanager
from functools import wraps
from time import perf_counter

_active = ContextVar('ledger_performance', default=None)

class Profile:
    def __init__(self):
        self.seconds, self.counts = {}, {}

    def snapshot(self):
        return {'seconds': dict(self.seconds), 'counts': dict(self.counts)}

    def __enter__(self):
        self.token = _active.set(self)
        return self

    def __exit__(self, *args):
        _active.reset(self.token)

def count(key, amount=1):
    p = _active.get()
    if p is not None:
        p.counts[key] = p.counts.get(key, 0)+amount

def snapshot():
    p = _active.get()
    return p.snapshot() if p is not None else {'seconds': {}, 'counts': {}}

@contextmanager
def measure(key):
    p = _active.get()
    if p is None:
        yield
        return
    start = perf_counter()
    try:
        yield
    finally:
        p.seconds[key] = p.seconds.get(key, 0)+perf_counter()-start
        p.counts[key] = p.counts.get(key, 0)+1

def timed(key):
    def decorate(fn):
        @wraps(fn)
        def call(*args, **kwargs):
            with measure(key):
                return fn(*args, **kwargs)
        return call
    return decorate

def profiled(fn):
    @wraps(fn)
    def call(*args, **kwargs):
        if _active.get() is not None:
            return fn(*args, **kwargs)
        with Profile() as p:
            result = fn(*args, **kwargs)
            result['performance'] = p.snapshot()
            return result
    return call
