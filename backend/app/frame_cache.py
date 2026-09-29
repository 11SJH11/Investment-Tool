"""Bounded process-local input frames; never caches strategies or results."""
from collections import OrderedDict
from hashlib import sha256
import os
from threading import RLock
from time import monotonic

import pandas as pd
from app.performance import count


class FrameCache:
    def __init__(self, max_entries=32, max_bytes=256 * 1024 * 1024, ttl=120):
        self.max_entries, self.max_bytes, self.ttl = max_entries, max_bytes, ttl
        self.entries = OrderedDict()
        self.lock = RLock()
        self.bytes = 0

    def _remove(self, key):
        self.bytes -= self.entries.pop(key)[2]

    def clear(self):
        with self.lock:
            self.entries.clear()
            self.bytes = 0

    def get(self, key):
        with self.lock:
            item = self.entries.get(key)
            if item and monotonic() - item[0] >= self.ttl:
                self._remove(key)
                item = None
            count('frame_cache_hit' if item else 'frame_cache_miss')
            if item is None:
                return None
            self.entries.move_to_end(key)
            return item[1].copy(deep=True)

    def put(self, key, frame):
        size = int(frame.memory_usage(index=True, deep=True).sum())
        with self.lock:
            if key in self.entries:
                self._remove(key)
            if self.max_entries <= 0 or size > self.max_bytes:
                return
            now = monotonic()
            for old in list(self.entries):
                if now - self.entries[old][0] >= self.ttl:
                    self._remove(old)
            while self.entries and (len(self.entries) >= self.max_entries or self.bytes + size > self.max_bytes):
                self._remove(next(iter(self.entries)))
            self.entries[key] = (now, frame.copy(deep=True), size)
            self.bytes += size

    def range_get(self, identity, start, end):
        with self.lock:
            for key in reversed(list(self.entries)):
                if isinstance(key, tuple) and len(key) == 4 and key[:2] == ('range', identity):
                    if key[2] <= start and key[3] >= end:
                        frame = self.get(key)
                        if frame is not None:
                            ts = pd.to_datetime(frame.timestamp, utc=True)
                            return frame.loc[(ts >= start) & (ts <= end)].reset_index(drop=True)
            count('frame_cache_miss')
        return None

    def stats(self):
        with self.lock:
            return {'entries': len(self.entries), 'approx_bytes': self.bytes,
                    'max_bytes': self.max_bytes, 'ttl_seconds': self.ttl}


def fingerprint(frame):
    """All scalar input values, provenance, dtypes and column order participate."""
    digest = sha256(repr([(c, str(d)) for c, d in frame.dtypes.items()]).encode())
    digest.update(pd.util.hash_pandas_object(frame, index=True).values.tobytes())
    return digest.hexdigest()


frames = FrameCache(max_entries=int(os.getenv('LEDGER_FRAME_CACHE_ENTRIES', '32')),
                    max_bytes=int(os.getenv('LEDGER_FRAME_CACHE_MB', '256')) * 1024 * 1024,
                    ttl=float(os.getenv('LEDGER_FRAME_CACHE_TTL', '120')))
