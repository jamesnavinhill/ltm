from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from typing import Optional


class TtlLruCache:
    def __init__(self, max_size: int = 512, ttl_seconds: int = 300):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._store: OrderedDict[str, float] = OrderedDict()

    def _evict_expired(self):
        now = time.time()
        keys_to_delete = [k for k, ts in self._store.items() if (now - ts) > self.ttl_seconds]
        for k in keys_to_delete:
            self._store.pop(k, None)

    def _evict_lru(self):
        while len(self._store) > self.max_size:
            self._store.popitem(last=False)

    def seen(self, key: str) -> bool:
        self._evict_expired()
        if key in self._store:
            # refresh recency
            self._store.move_to_end(key, last=True)
            return True
        return False

    def add(self, key: str):
        self._evict_expired()
        self._store[key] = time.time()
        self._store.move_to_end(key, last=True)
        self._evict_lru()


def compute_text_hash(normalized_text: str) -> str:
    return hashlib.md5(normalized_text.encode("utf-8")).hexdigest()


def normalize_text(raw_text: str) -> str:
    # Basic normalization: strip, collapse whitespace lines, drop empties
    lines = [ln.strip() for ln in raw_text.splitlines()]
    lines = [ln for ln in lines if ln]
    # Limit repeated adjacent lines
    collapsed = []
    last: Optional[str] = None
    for ln in lines:
        if ln != last:
            collapsed.append(ln)
            last = ln
    return "\n".join(collapsed).strip()


