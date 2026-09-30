"""One application-owned CPU reservation budget, shared by all run paths."""
from contextlib import contextmanager
from threading import Condition, local


class SimulationBudget:
    def __init__(self, limit):
        self.limit = limit
        self.condition = Condition()
        self.used = 0
        self.peak = 0
        self.waiting = 0
        self.local = local()

    def snapshot(self):
        with self.condition:
            return {'used_workers': self.used, 'peak_reserved_workers': self.peak,
                    'waiting_reservations': self.waiting, 'configured_budget': self.limit()}

    def notify(self):
        with self.condition: self.condition.notify_all()

    @contextmanager
    def reserve(self, requested=1, cancelled=lambda: None):
        # Ordinary queue work calls the same service as the direct API. A nested
        # engine reservation reuses that thread's lease instead of double counting.
        if getattr(self.local, 'reserved', 0):
            yield self.local.reserved
            return
        granted = 0
        with self.condition:
            self.waiting += 1
            try:
                while not granted:
                    cancelled()
                    available = max(0, self.limit()-self.used)
                    if available:
                        granted = min(max(1, int(requested)), available)
                        self.used += granted
                        self.peak = max(self.peak, self.used)
                        self.local.reserved = granted
                    else:
                        self.condition.wait(.1)
            finally:
                self.waiting -= 1
        try:
            yield granted
        finally:
            with self.condition:
                self.local.reserved = 0
                self.used -= granted
                self.condition.notify_all()
