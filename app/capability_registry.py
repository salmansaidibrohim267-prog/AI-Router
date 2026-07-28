"""Capability Registry — loads models_registry.yaml and provides capability lookups with hot reload."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


REGISTRY_PATH = Path(__file__).resolve().parent.parent / "config" / "models_registry.yaml"


@dataclass
class ModelCapability:
    provider: str
    model: str
    context_window: int = 4096
    supports_streaming: bool = False
    supports_tools: bool = False
    supports_vision: bool = False
    supports_json_mode: bool = False
    supports_embeddings: bool = False
    supports_reasoning: bool = False
    supports_thinking: bool = False
    supports_image_generation: bool = False
    supports_function_calling: bool = False

    def has(self, capability: str) -> bool:
        attr = f"supports_{capability}"
        return bool(getattr(self, attr, False))

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "context_window": self.context_window,
            "supports_streaming": self.supports_streaming,
            "supports_tools": self.supports_tools,
            "supports_vision": self.supports_vision,
            "supports_json_mode": self.supports_json_mode,
            "supports_embeddings": self.supports_embeddings,
            "supports_reasoning": self.supports_reasoning,
            "supports_thinking": self.supports_thinking,
            "supports_image_generation": self.supports_image_generation,
            "supports_function_calling": self.supports_function_calling,
        }


CAPABILITY_FIELDS = {
    "streaming", "tools", "vision", "json_mode", "embeddings",
    "reasoning", "thinking", "image_generation", "function_calling",
}


class CapabilityRegistry:
    """Loads and queries model capabilities from models_registry.yaml."""

    def __init__(self, path: str | Path | None = None):
        self._path = Path(path) if path else REGISTRY_PATH
        self._entries: dict[str, ModelCapability] = {}
        self._lock = threading.RLock()
        self._last_mtime: float = 0
        self._watch_active = False
        self._reload_callbacks: list[callable] = []
        self._load()

    def _key(self, provider: str, model: str) -> str:
        return f"{provider}::{model}"

    def _load(self) -> None:
        if not self._path.exists():
            self._entries = {}
            return
        with open(self._path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        raw_list = data.get("models", [])
        entries: dict[str, ModelCapability] = {}
        for item in raw_list:
            prov = (item.get("provider") or "").strip()
            mod = (item.get("model") or "").strip()
            if not prov or not mod:
                continue
            entries[self._key(prov, mod)] = ModelCapability(
                provider=prov,
                model=mod,
                context_window=item.get("context_window", 4096),
                supports_streaming=bool(item.get("supports_streaming", False)),
                supports_tools=bool(item.get("supports_tools", False)),
                supports_vision=bool(item.get("supports_vision", False)),
                supports_json_mode=bool(item.get("supports_json_mode", False)),
                supports_embeddings=bool(item.get("supports_embeddings", False)),
                supports_reasoning=bool(item.get("supports_reasoning", False)),
                supports_thinking=bool(item.get("supports_thinking", False)),
                supports_image_generation=bool(item.get("supports_image_generation", False)),
                supports_function_calling=bool(item.get("supports_function_calling", False)),
            )
        self._entries = entries

    @staticmethod
    def _strip_prefix(model: str) -> str:
        return model.split("/")[-1] if "/" in model else model

    def get(self, provider: str, model: str) -> ModelCapability | None:
        """Look up a model by provider + model name."""
        m = self._strip_prefix(model)
        return self._entries.get(self._key(provider, m))

    def get_by_model(self, model: str) -> ModelCapability | None:
        """Look up a model by model name across all providers (first match)."""
        m = self._strip_prefix(model)
        for cap in self._entries.values():
            if cap.model == m:
                return cap
        return None

    def has_capability(self, provider: str, model: str, capability: str) -> bool:
        cap = self.get(provider, model)
        if cap is None:
            cap = self.get_by_model(model)
        if cap is None:
            return True
        return cap.has(capability)

    def get_context_window(self, provider: str, model: str) -> int | None:
        cap = self.get(provider, model)
        if cap is None:
            cap = self.get_by_model(model)
        return cap.context_window if cap else None

    def filter_candidates(
        self,
        candidates: list[tuple[str, str]],
        required: set[str],
    ) -> list[tuple[str, str]]:
        """Filter provider-model pairs to only those supporting all required capabilities."""
        if not required:
            return list(candidates)
        result: list[tuple[str, str]] = []
        for provider, model in candidates:
            ok = True
            for cap in required:
                if not self.has_capability(provider, model, cap):
                    ok = False
                    break
            if ok:
                result.append((provider, model))
        return result

    def get_all_models(self) -> list[ModelCapability]:
        return list(self._entries.values())

    def get_providers(self) -> list[str]:
        provs: set[str] = set()
        for cap in self._entries.values():
            provs.add(cap.provider)
        return sorted(provs)

    def get_models_by_provider(self, provider: str) -> list[ModelCapability]:
        return [cap for cap in self._entries.values() if cap.provider == provider]

    # === Hot reload ===

    def reload(self) -> bool:
        try:
            self._load()
            self._last_mtime = time.time()
            return True
        except Exception:
            return False

    def enable_watcher(self, callback: callable | None = None) -> None:
        self._watch_active = True
        if callback:
            self._reload_callbacks.append(callback)

        def watch_loop():
            while self._watch_active:
                try:
                    current_mtime = 0
                    if self._path.exists():
                        current_mtime = os.path.getmtime(self._path)
                    if self._last_mtime > 0 and current_mtime > self._last_mtime:
                        time.sleep(0.3)
                        if self.reload():
                            for cb in self._reload_callbacks:
                                try:
                                    cb()
                                except Exception:
                                    pass
                    self._last_mtime = current_mtime
                except Exception:
                    pass
                time.sleep(2)

        thread = threading.Thread(target=watch_loop, daemon=True)
        thread.start()

    def disable_watcher(self) -> None:
        self._watch_active = False

    def __len__(self) -> int:
        return len(self._entries)


capability_registry = CapabilityRegistry()
