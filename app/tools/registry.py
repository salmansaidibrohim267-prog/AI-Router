from __future__ import annotations

import importlib
import pkgutil
from typing import Any

from app.tools.base import Tool, ToolSpec


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.spec.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def get_all(self) -> dict[str, Tool]:
        return dict(self._tools)

    def list_specs(self) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values()]

    def has(self, name: str) -> bool:
        return name in self._tools

    def clear(self) -> None:
        self._tools.clear()

    def discover(self, package: str = "app.tools.builtins") -> list[str]:
        discovered = []
        try:
            mod = importlib.import_module(package)
            for _, name, is_pkg in pkgutil.iter_modules(mod.__path__):
                if not is_pkg:
                    try:
                        tool_mod = importlib.import_module(f"{package}.{name}")
                        for attr in dir(tool_mod):
                            cls = getattr(tool_mod, attr)
                            if isinstance(cls, type) and issubclass(cls, Tool) and cls is not Tool:
                                instance = cls()
                                self.register(instance)
                                discovered.append(instance.spec.name)
                    except Exception:
                        pass
        except ImportError:
            pass
        return discovered
