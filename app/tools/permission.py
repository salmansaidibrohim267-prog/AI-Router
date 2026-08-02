from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class PermissionRule:
    def __init__(
        self,
        tool_name: str = "",
        allowed_users: list[str] | None = None,
        allowed_roles: list[str] | None = None,
        max_calls: int = 0,
        require_approval: bool = False,
    ):
        self.tool_name = tool_name
        self.allowed_users = allowed_users or []
        self.allowed_roles = allowed_roles or []
        self.max_calls = max_calls
        self.require_approval = require_approval


ALLOW_ALL = PermissionRule()


class PermissionManager:
    def __init__(self):
        self._rules: dict[str, PermissionRule] = {}
        self._call_counts: dict[str, int] = {}

    def grant(self, tool_name: str, rule: PermissionRule) -> None:
        self._rules[tool_name] = rule

    def revoke(self, tool_name: str) -> None:
        self._rules.pop(tool_name, None)

    def check(
        self,
        tool_name: str,
        user: str = "",
        role: str = "",
    ) -> tuple[bool, str]:
        rule = self._rules.get(tool_name, ALLOW_ALL)
        if rule.allowed_users and user and user not in rule.allowed_users:
            msg = f"User '{user}' not allowed to use tool '{tool_name}'"
            logger.warning(msg)
            return False, msg
        if rule.allowed_roles and role and role not in rule.allowed_roles:
            msg = f"Role '{role}' not allowed to use tool '{tool_name}'"
            logger.warning(msg)
            return False, msg
        if rule.max_calls > 0:
            count = self._call_counts.get(tool_name, 0)
            if count >= rule.max_calls:
                msg = f"Tool '{tool_name}' call limit ({rule.max_calls}) reached"
                logger.warning(msg)
                return False, msg
        return True, ""

    def record_call(self, tool_name: str) -> None:
        self._call_counts[tool_name] = self._call_counts.get(tool_name, 0) + 1

    def get_stats(self) -> dict[str, Any]:
        return {
            "rules": list(self._rules.keys()),
            "call_counts": dict(self._call_counts),
        }
