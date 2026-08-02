from __future__ import annotations

from typing import Any

from .manager import PluginManager
from .models import PluginStatus


class PluginManagerSource:
    """Adapter exposing the plugin platform to the admin dashboard.

    Compatible with ``app.admin.PluginsModule(source=...)`` which expects
    ``get_enabled()`` (objects with a ``name`` attribute) and ``disabled()``
    (list of names).
    """

    def __init__(self, manager: PluginManager) -> None:
        self._manager = manager

    def get_enabled(self) -> list[Any]:
        return [info for info in self._manager.list() if info.status == PluginStatus.ENABLED]

    def disabled(self) -> list[str]:
        return [info.name for info in self._manager.list() if info.status != PluginStatus.ENABLED]
