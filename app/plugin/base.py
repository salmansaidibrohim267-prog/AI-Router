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

    async def initialize(self) -> None:
        pass

    async def before_request(self, request: Any, context: dict[str, Any]) -> HookResult:
        return HookResult()

    async def after_response(
        self, request: Any, response: Any, context: dict[str, Any]
    ) -> HookResult:
        return HookResult()

    async def on_error(
        self, request: Any, error: Exception, context: dict[str, Any]
    ) -> HookResult:
        return HookResult()

    async def shutdown(self) -> None:
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name} v{self.version}>"
