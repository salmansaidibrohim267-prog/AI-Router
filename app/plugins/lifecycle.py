from __future__ import annotations

import threading

from .exceptions import PluginLifecycleError
from .logging import PluginLogger
from .models import PluginStatus

_VALID_TRANSITIONS: dict[PluginStatus, set[PluginStatus]] = {
    PluginStatus.DRAFT: {PluginStatus.INSTALLING, PluginStatus.FAILED},
    PluginStatus.INSTALLING: {PluginStatus.INSTALLED, PluginStatus.FAILED},
    PluginStatus.INSTALLED: {PluginStatus.VERIFYING, PluginStatus.UNINSTALLING, PluginStatus.FAILED},
    PluginStatus.VERIFYING: {PluginStatus.VERIFIED, PluginStatus.FAILED},
    PluginStatus.VERIFIED: {
        PluginStatus.ENABLING,
        PluginStatus.DISABLED,
        PluginStatus.UPDATING,
        PluginStatus.UNINSTALLING,
        PluginStatus.FAILED,
    },  # noqa: E501
    PluginStatus.ENABLING: {PluginStatus.ENABLED, PluginStatus.FAILED},
    PluginStatus.ENABLED: {PluginStatus.DISABLED, PluginStatus.UPDATING, PluginStatus.UNINSTALLING},
    PluginStatus.DISABLED: {PluginStatus.ENABLING, PluginStatus.UPDATING, PluginStatus.UNINSTALLING},
    PluginStatus.UPDATING: {
        PluginStatus.ENABLED,
        PluginStatus.DISABLED,
        PluginStatus.ROLLING_BACK,
        PluginStatus.FAILED,
    },  # noqa: E501
    PluginStatus.ROLLING_BACK: {
        PluginStatus.ENABLED,
        PluginStatus.DISABLED,
        PluginStatus.ROLLED_BACK,
        PluginStatus.FAILED,
    },  # noqa: E501
    PluginStatus.ROLLED_BACK: {
        PluginStatus.ENABLING,
        PluginStatus.DISABLED,
        PluginStatus.UNINSTALLING,
        PluginStatus.UPDATING,
    },  # noqa: E501
    PluginStatus.UNINSTALLING: {PluginStatus.UNINSTALLED, PluginStatus.FAILED},
    PluginStatus.UNINSTALLED: set(),
    PluginStatus.FAILED: {PluginStatus.UNINSTALLING, PluginStatus.INSTALLING},
}


class PluginLifecycle:
    """Per-plugin lifecycle state machine.

    Transitions are validated against the allowed map; invalid transitions
    raise ``PluginLifecycleError``.
    """

    def __init__(self, logger: PluginLogger | None = None) -> None:
        self._logger = logger or PluginLogger()
        self._states: dict[str, PluginStatus] = {}
        self._lock = threading.Lock()

    def initialize(self, name: str, status: PluginStatus = PluginStatus.DRAFT) -> None:
        with self._lock:
            self._states[name] = status

    def state(self, name: str) -> PluginStatus:
        with self._lock:
            return self._states.get(name, PluginStatus.DRAFT)

    def is_installed(self, name: str) -> bool:
        return self.state(name) in (
            PluginStatus.INSTALLED,
            PluginStatus.ENABLED,
            PluginStatus.DISABLED,
            PluginStatus.VERIFIED,
            PluginStatus.ROLLED_BACK,
        )  # noqa: E501

    def is_enabled(self, name: str) -> bool:
        return self.state(name) == PluginStatus.ENABLED

    def can_transition(self, name: str, to: PluginStatus) -> bool:
        return to in _VALID_TRANSITIONS[self.state(name)]

    def transition(self, name: str, to: PluginStatus) -> PluginStatus:
        current = self.state(name)
        if to not in _VALID_TRANSITIONS[current]:
            raise PluginLifecycleError(
                f"invalid plugin {name!r} lifecycle transition {current.value} -> {to.value}",
                plugin=name,
                from_status=current.value,
                to_status=to.value,
            )
        with self._lock:
            self._states[name] = to
        self._logger.log_event("lifecycle.transition", plugin=name, from_status=current.value, to_status=to.value)
        return to

    def drop(self, name: str) -> None:
        with self._lock:
            self._states.pop(name, None)

    def states(self) -> dict[str, str]:
        with self._lock:
            return {name: status.value for name, status in self._states.items()}
