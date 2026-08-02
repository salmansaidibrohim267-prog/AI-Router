from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.tools.base import Tool, ToolResult
from app.tools.models import ToolCall, ToolResponse
from app.tools.permission import PermissionManager
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        permission: PermissionManager | None = None,
    ):
        self._registry = registry
        self._permission = permission or PermissionManager()

    async def execute(
        self,
        tool_name: str,
        input_data: str = "",
        call_id: str = "",
        user: str = "",
        role: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ToolResponse:
        tool = self._registry.get(tool_name)
        if not tool:
            return ToolResponse(
                tool_name=tool_name,
                success=False,
                error=f"Unknown tool: {tool_name}",
            )

        allowed, msg = self._permission.check(tool_name, user=user, role=role)
        if not allowed:
            return ToolResponse(
                tool_name=tool_name,
                success=False,
                error=msg,
            )

        if metadata is None:
            metadata = {}
        call = ToolCall(
            tool_name=tool_name,
            input=input_data,
            call_id=call_id,
            metadata=metadata,
        )

        start = time.perf_counter()
        try:
            response = await asyncio.wait_for(
                tool.execute(call),
                timeout=tool.spec.timeout,
            )
        except asyncio.TimeoutError:
            elapsed = (time.perf_counter() - start) * 1000
            logger.warning(f"Tool '{tool_name}' timed out after {tool.spec.timeout}s")
            response = ToolResponse(
                tool_name=tool_name,
                success=False,
                error=f"Timed out after {tool.spec.timeout}s",
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.exception(f"Tool '{tool_name}' execution error: {e}")
            response = ToolResponse(
                tool_name=tool_name,
                success=False,
                error=str(e),
                duration_ms=elapsed,
            )

        self._permission.record_call(tool_name)
        return response

    def get_definitions(self) -> list[dict[str, Any]]:
        return [t.spec.to_openai_format() for t in self._registry.get_all().values()]
