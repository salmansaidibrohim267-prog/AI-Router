import time
import pytest
from app.cache import TTLCache, CacheManager


class TestTTLCache:
    def setup_method(self):
        self.cache = TTLCache("test", max_size=100, default_ttl=300)

    def test_set_and_get(self):
        self.cache.set("key1", "value1")
        assert self.cache.get("key1") == "value1"

    def test_get_missing(self):
        assert self.cache.get("nonexistent") is None

    def test_get_stats(self):
        stats = self.cache.get_stats()
        assert stats.name == "test"
        assert stats.hits == 0
        assert stats.misses == 0

    def test_hit_count(self):
        self.cache.set("key", "val")
        self.cache.get("key")
        stats = self.cache.get_stats()
        assert stats.hits == 1

    def test_miss_count(self):
        self.cache.get("missing")
        stats = self.cache.get_stats()
        assert stats.misses == 1

    def test_delete(self):
        self.cache.set("key", "val")
        assert self.cache.delete("key") is True
        assert self.cache.get("key") is None

    def test_delete_missing(self):
        assert self.cache.delete("nonexistent") is False

    def test_clear(self):
        self.cache.set("k1", "v1")
        self.cache.set("k2", "v2")
        self.cache.clear()
        assert self.cache.get("k1") is None
        assert self.cache.get("k2") is None

    def test_expired_entry(self):
        self.cache.set("key", "val", ttl=1)
        key = self.cache._make_key("key")
        self.cache._cache[key].expires_at = time.time() - 1
        assert self.cache.get("key") is None

    def test_lru_eviction(self):
        small = TTLCache("small", max_size=2, default_ttl=300)
        small.set("a", 1)
        small.set("b", 2)
        small.set("c", 3)
        assert small.get("a") is None
        assert small.get("b") == 2
        assert small.get("c") == 3

    def test_hit_rate(self):
        self.cache.get("m1")
        self.cache.get("m2")
        self.cache.get("m3")
        stats = self.cache.get_stats()
        assert stats.hit_rate == 0.0


class TestCacheManager:
    def setup_method(self):
        self.mgr = CacheManager()

    def test_get_cache_creates_new(self):
        c = self.mgr.get_cache("new")
        assert c.name == "new"

    def test_get_cache_reuses_existing(self):
        c1 = self.mgr.get_cache("same")
        c2 = self.mgr.get_cache("same")
        assert c1 is c2

    def test_get_all_stats_empty(self):
        assert self.mgr.get_all_stats() == {}

    def test_clear_all(self):
        c = self.mgr.get_cache("test")
        c.set("key", "val")
        self.mgr.clear_all()
        assert c.get("key") is None
