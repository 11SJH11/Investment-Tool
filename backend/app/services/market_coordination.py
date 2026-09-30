"""Reentrant provider coordination with priority for interactive requests."""
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Condition, get_ident

_background = ContextVar('market_background', default=None)


class WarmupPaused(Exception):
    pass


@contextmanager
def background_market_work(check_cancelled):
    token = _background.set(check_cancelled)
    try:
        yield
    finally:
        _background.reset(token)


class ProviderPriorityLock:
    def __init__(self):
        self.condition = Condition()
        self.owner = None
        self.depth = 0
        self.interactive_waiters = 0

    def __enter__(self):
        owner = get_ident()
        background = _background.get()
        with self.condition:
            if self.owner == owner:
                self.depth += 1
                return self
            if background is None:
                self.interactive_waiters += 1
            try:
                while self.owner is not None or (background is not None and self.interactive_waiters):
                    if background is not None:
                        background()
                    self.condition.wait(.1)
                if background is not None:
                    background()
                self.owner, self.depth = owner, 1
            finally:
                if background is None:
                    self.interactive_waiters -= 1
                self.condition.notify_all()
        return self

    def __exit__(self, *args):
        with self.condition:
            self.depth -= 1
            if not self.depth:
                self.owner = None
                self.condition.notify_all()
