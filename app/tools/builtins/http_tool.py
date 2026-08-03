from __future__ import annotations

import httpx

from app.tools.base import Tool, ToolCall, ToolResponse, ToolSpec


class HTTPTool(Tool):
    spec = ToolSpec(
        name="http",
        description="Make HTTP requests (GET, POST, PUT, DELETE)",
        parameters={
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "URL to request"},
                "method": {
                    "type": "string",
                    "description": "HTTP method (GET, POST, PUT, DELETE)",
                    "enum": ["GET", "POST", "PUT", "DELETE"],
                },  # noqa: E501
                "body": {"type": "string", "description": "Request body (for POST/PUT)"},
            },
            "required": ["input"],
        },
        required_permissions=["http"],
        timeout=30,
    )

    async def execute(self, call: ToolCall) -> ToolResponse:
        url = call.input.strip()
        method = call.arguments.get("method", "GET").upper()
        body = call.arguments.get("body", None)
        if not url:
            return ToolResponse(
                tool_name=self.spec.name,
                success=False,
                error="No URL provided",
            )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if method == "GET":
                    resp = await client.get(url)
                elif method == "POST":
                    resp = await client.post(url, content=body)
                elif method == "PUT":
                    resp = await client.put(url, content=body)
                elif method == "DELETE":
                    resp = await client.delete(url)
                else:
                    return ToolResponse(
                        tool_name=self.spec.name,
                        success=False,
                        error=f"Unsupported method: {method}",
                    )
                content = resp.text[:5000]
                if resp.is_success:
                    return ToolResponse(
                        tool_name=self.spec.name,
                        success=True,
                        output=content,
                        metadata={"status_code": resp.status_code},
                    )
                return ToolResponse(
                    tool_name=self.spec.name,
                    success=False,
                    error=f"HTTP {resp.status_code}: {content[:500]}",
                )
        except Exception as e:
            return ToolResponse(
                tool_name=self.spec.name,
                success=False,
                error=str(e),
            )
