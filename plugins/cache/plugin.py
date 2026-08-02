import json
import time
from collections import OrderedDict
from hashlib import sha256

from app.plugin.base import AIPlugin, HookResult


class CachePlugin(AIPlugin):
    name = "cache"
    version = "1.0.0"
    description = "Response caching plugin for reducing duplicate requests"

    def __init__(self):
        self._cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._max_size = 100
        self._ttl = 300

    async def initialize(self) -> None:
        self._cache.clear()

    async def before_request(self, request, context) -> HookResult:
        cache_key = self._make_key(request)
        cached = self._get(cache_key)
        if cached is not None:
            return HookResult(
                should_cancel=False,
                modified_response=cached,
                metadata={"cache_hit": True, "plugin": "cache"},
            )
        context["_cache_key"] = cache_key
        return HookResult(metadata={"cache_miss": True, "plugin": "cache"})

    async def after_response(self, request, response, context) -> HookResult:
        cache_key = context.pop("_cache_key", None)
        if cache_key and response:
            self._set(cache_key, response)
        return HookResult()

    def _make_key(self, request) -> str:
        raw = json.dumps(
            {
                "model": getattr(request, "model", ""),
                "messages": getattr(request, "messages", []),
                "temperature": getattr(request, "temperature", None),
                "max_tokens": getattr(request, "max_tokens", None),
            },
            sort_keys=True,
            default=str,
        )
        return sha256(raw.encode()).hexdigest()

    def _get(self, key: str) -> dict | None:
        if key not in self._cache:
            return None
        timestamp, value = self._cache[key]
        if time.time() - timestamp > self._ttl:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return value

    def _set(self, key: str, value: dict) -> None:
        if len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)
        self._cache[key] = (time.time(), value)

    async def shutdown(self) -> None:
        self._cache.clear()
