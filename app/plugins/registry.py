from __future__ import annotations

import threading
from typing import Any

from .exceptions import ExtensionAlreadyRegisteredError, ExtensionNotFoundError
from .models import Extension, ExtensionKind


class ExtensionRegistry:
    """Stores plugin-registered extensions by kind, tracking ownership.

    Each extension records the plugin that registered it so uninstall and
    rollback can clean up cleanly.
    """

    def __init__(self) -> None:
        self._extensions: dict[str, dict[str, Extension]] = {}
        self._lock = threading.Lock()

    def register(self, extension: Extension) -> Extension:
        key = extension.kind.value
        with self._lock:
            bucket = self._extensions.setdefault(key, {})
            if extension.name in bucket:
                raise ExtensionAlreadyRegisteredError(
                    f"{extension.kind.value} {extension.name!r} already registered", kind=extension.kind.value, name=extension.name
                )
            bucket[extension.name] = extension
        return extension

    def unregister(self, kind: ExtensionKind | str, name: str) -> bool:
        key = kind.value if isinstance(kind, ExtensionKind) else kind
        with self._lock:
            bucket = self._extensions.get(key, {})
            if name not in bucket:
                return False
            del bucket[name]
            if not bucket:
                self._extensions.pop(key, None)
            return True

    def unregister_plugin(self, plugin: str) -> int:
        removed = 0
        with self._lock:
            for key, bucket in list(self._extensions.items()):
                for name in [name for name, ext in bucket.items() if ext.plugin == plugin]:
                    del bucket[name]
                    removed += 1
                if not bucket:
                    self._extensions.pop(key, None)
        return removed

    def get(self, kind: ExtensionKind | str, name: str) -> Extension:
        key = kind.value if isinstance(kind, ExtensionKind) else kind
        with self._lock:
            extension = self._extensions.get(key, {}).get(name)
        if extension is None:
            raise ExtensionNotFoundError(f"{key} extension {name!r} not found", kind=key, name=name)
        return extension

    def get_or_none(self, kind: ExtensionKind | str, name: str) -> Extension | None:
        key = kind.value if isinstance(kind, ExtensionKind) else kind
        with self._lock:
            return self._extensions.get(key, {}).get(name)

    def list(self, kind: ExtensionKind | str | None = None) -> list[Extension]:
        with self._lock:
            if kind is None:
                return [extension for bucket in self._extensions.values() for extension in bucket.values()]
            key = kind.value if isinstance(kind, ExtensionKind) else kind
            return list(self._extensions.get(key, {}).values())

    def list_by_plugin(self, plugin: str) -> list[Extension]:
        with self._lock:
            return [extension for bucket in self._extensions.values() for extension in bucket.values() if extension.plugin == plugin]

    def count(self) -> int:
        with self._lock:
            return sum(len(bucket) for bucket in self._extensions.values())

    def count_by_kind(self) -> dict[str, int]:
        with self._lock:
            return {key: len(bucket) for key, bucket in self._extensions.items()}
