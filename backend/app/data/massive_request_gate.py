"""One process-wide API budget per Massive key, shared by all endpoint types."""
from hashlib import sha256
from threading import Lock
import time

from app.data.http import ProviderHttpError

_guard = Lock()
_budgets = {}


class MassiveRequestGate:
    def __init__(self, http, key, *, calls_per_minute=5, clock=time.monotonic, sleep=time.sleep):
        self.http, self.clock, self.sleep = http, clock, sleep
        self.interval = 60 / calls_per_minute + .25
        with _guard:
            self.state = _budgets.setdefault(sha256(key.encode()).hexdigest(), {'lock': Lock(), 'ready': 0})

    def get_json(self, url, **kwargs):
        with self.state['lock']:
            # One paced recovery attempt handles a cold-cache first 429. Unlike
            # subsecond HTTP retries, the entire provider respects the cooldown.
            for attempt in range(2):
                self.sleep(max(0, self.state['ready'] - self.clock()))
                self.state['ready'] = self.clock() + self.interval
                try:
                    return self.http.get_json(url, **kwargs, max_attempts=1)
                except ProviderHttpError as exc:
                    if exc.status_code != 429:
                        raise
                    delay = max(60, exc.retry_after or 0)
                    self.state['ready'] = self.clock() + delay
                    if attempt or delay > 120:
                        raise ProviderHttpError('Massive API quota is temporarily exhausted. Cached data is retained; retry after the provider cooldown.', status_code=429, retry_after=delay) from None
