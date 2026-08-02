from __future__ import annotations

from app.tools.base import Tool, ToolCall, ToolResponse, ToolSpec


class SearchTool(Tool):
    spec = ToolSpec(
        name="search",
        description="Search the web for information (simulated)",
        parameters={
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Search query"},
            },
            "required": ["input"],
        },
        required_permissions=["search"],
        timeout=15,
    )

    async def execute(self, call: ToolCall) -> ToolResponse:
        query = call.input.strip()
        if not query:
            return ToolResponse(
                tool_name=self.spec.name,
                success=False,
                error="No search query provided",
            )
        return ToolResponse(
            tool_name=self.spec.name,
            success=True,
            output=f"[Search results for: {query[:200]}]",
        )
