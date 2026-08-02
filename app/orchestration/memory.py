from __future__ import annotations

from typing import Any


class ExecutionMemory:
    def __init__(self):
        self._store: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def get_all(self) -> dict[str, Any]:
        return dict(self._store)

    def update(self, data: dict[str, Any]) -> None:
        self._store.update(data)

    def clear(self) -> None:
        self._store.clear()

    def keys(self) -> list[str]:
        return list(self._store.keys())

    def __contains__(self, key: str) -> bool:
        return key in self._store

    def __len__(self) -> int:
        return len(self._store)

    def resolve_refs(self, text: str) -> str:
        import re
        def _replace(match):
            key = match.group(1)
            val = self.get(key, "")
            return str(val) if val is not None else ""
        return re.sub(r"\{\{([^}]+)\}\}", _replace, text)
