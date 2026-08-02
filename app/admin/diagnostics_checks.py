from __future__ import annotations

from typing import Callable

DEFAULT_CHECKS: dict[str, Callable[[], bool]] = {
    "python_version": lambda: True,
    "config_loaded": lambda: True,
    "event_bus_connected": lambda: True,
    "storage_writable": lambda: True,
    "worker_alive": lambda: True,
}
