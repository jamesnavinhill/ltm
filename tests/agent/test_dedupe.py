from __future__ import annotations

import time

from plans.agent_prototype.dedupe import TtlLruCache, compute_text_hash, normalize_text


def test_normalize_text_collapses_and_removes_empties():
    raw = "\nHello\n\nHello\nWorld\nWorld\n \n"
    norm = normalize_text(raw)
    assert norm.splitlines() == ["Hello", "World"]


def test_compute_text_hash_deterministic():
    a = compute_text_hash("foo")
    b = compute_text_hash("foo")
    c = compute_text_hash("bar")
    assert a == b
    assert a != c


def test_ttl_cache_expiration_and_lru_evict():
    cache = TtlLruCache(max_size=2, ttl_seconds=0.1)
    cache.add("a")
    assert cache.seen("a") is True

    # Expire
    time.sleep(0.12)
    assert cache.seen("a") is False

    # LRU eviction
    cache = TtlLruCache(max_size=2, ttl_seconds=10)
    cache.add("a")
    cache.add("b")
    cache.add("c")  # should evict 'a'
    assert cache.seen("a") is False
    assert cache.seen("b") is True
    assert cache.seen("c") is True


