from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HookResult:
    should_cancel: bool = False
    cancel_reason: str = ""
    modified_request: Any = None
    modified_response: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AIPlugin:
    name: str = "base"
    version: str = "0.1.0"
    description: str = ""
    _plugin_enabled: bool = True

    async def initialize(self) -> None:
        pass

    async def before_request(self, request: Any, context: dict[str, Any]) -> HookResult:
        return HookResult()

    async def before_route(self, request: Any, context: dict[str, Any]) -> HookResult:
        return HookResult()

    async def after_route(
        self,
        request: Any,
        context: dict[str, Any],
        routes: list[tuple[str, str]],
    ) -> HookResult:
        return HookResult()

    async def before_provider(
        self,
        request: Any,
        provider_name: str,
        model: str,
        context: dict[str, Any],
    ) -> HookResult:
        return HookResult()

    async def after_provider(
        self,
        request: Any,
        response: Any,
        provider_name: str,
        model: str,
        context: dict[str, Any],
    ) -> HookResult:
        return HookResult()

    async def before_response(self, request: Any, response: Any, context: dict[str, Any]) -> HookResult:
        return HookResult()

    async def after_response(self, request: Any, response: Any, context: dict[str, Any]) -> HookResult:
        return HookResult()

    async def on_error(self, request: Any, error: Exception, context: dict[str, Any]) -> HookResult:
        return HookResult()

    async def before_plan(self, request: Any, context: dict[str, Any]) -> HookResult:
        return HookResult()

    async def after_agent(
        self,
        agent_result: Any,
        agent_name: str,
        context: dict[str, Any],
    ) -> HookResult:
        return HookResult()

    async def before_reflection(
        self,
        agent_result: Any,
        context: dict[str, Any],
    ) -> HookResult:
        return HookResult()

    async def after_orchestrate(self, response: Any, context: dict[str, Any]) -> HookResult:
        return HookResult()

    async def shutdown(self) -> None:
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name} v{self.version}>"
