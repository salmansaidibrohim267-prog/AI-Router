from __future__ import annotations

import os
from pathlib import Path

from app.tools.base import Tool, ToolCall, ToolResponse, ToolSpec


class FilesystemTool(Tool):
    spec = ToolSpec(
        name="filesystem",
        description="Read, write, list files and directories",
        parameters={
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Operation and path, e.g. 'read /path/to/file' or 'write /path/to/file content' or 'ls /path'",  # noqa: E501
                },  # noqa: E501
            },
            "required": ["input"],
        },
        required_permissions=["filesystem"],
        timeout=30,
    )

    async def execute(self, call: ToolCall) -> ToolResponse:
        parts = call.input.strip().split(maxsplit=1)
        if not parts:
            return ToolResponse(
                tool_name=self.spec.name,
                success=False,
                error="Usage: read|write|ls|delete <path> [content]",
            )
        op = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""

        if op == "read":
            if not rest:
                return ToolResponse(
                    tool_name=self.spec.name,
                    success=False,
                    error="Path required",
                )
            p = Path(rest)
            if not p.exists():
                return ToolResponse(
                    tool_name=self.spec.name,
                    success=False,
                    error=f"Path not found: {rest}",
                )
            try:
                return ToolResponse(
                    tool_name=self.spec.name,
                    success=True,
                    output=p.read_text(encoding="utf-8"),
                )
            except Exception as e:
                return ToolResponse(
                    tool_name=self.spec.name,
                    success=False,
                    error=str(e),
                )

        elif op == "write":
            parts_w = rest.split(maxsplit=1)
            if len(parts_w) < 2:
                return ToolResponse(
                    tool_name=self.spec.name,
                    success=False,
                    error="Usage: write <path> <content>",
                )
            path, content = parts_w[0], parts_w[1]
            try:
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                Path(path).write_text(content, encoding="utf-8")
                return ToolResponse(
                    tool_name=self.spec.name,
                    success=True,
                    output=f"Written {len(content)} bytes to {path}",
                )
            except Exception as e:
                return ToolResponse(
                    tool_name=self.spec.name,
                    success=False,
                    error=str(e),
                )

        elif op == "ls":
            p = Path(rest or ".")
            if not p.exists():
                return ToolResponse(
                    tool_name=self.spec.name,
                    success=False,
                    error=f"Path not found: {rest or '.'}",
                )
            try:
                items = os.listdir(p)
                return ToolResponse(
                    tool_name=self.spec.name,
                    success=True,
                    output="\n".join(sorted(items)),
                )
            except Exception as e:
                return ToolResponse(
                    tool_name=self.spec.name,
                    success=False,
                    error=str(e),
                )

        elif op == "delete":
            if not rest:
                return ToolResponse(
                    tool_name=self.spec.name,
                    success=False,
                    error="Path required",
                )
            p = Path(rest)
            if not p.exists():
                return ToolResponse(
                    tool_name=self.spec.name,
                    success=False,
                    error=f"Path not found: {rest}",
                )
            try:
                if p.is_file():
                    p.unlink()
                else:
                    import shutil

                    shutil.rmtree(p)
                return ToolResponse(
                    tool_name=self.spec.name,
                    success=True,
                    output=f"Deleted {rest}",
                )
            except Exception as e:
                return ToolResponse(
                    tool_name=self.spec.name,
                    success=False,
                    error=str(e),
                )

        return ToolResponse(
            tool_name=self.spec.name,
            success=False,
            error=f"Unknown operation: {op}. Use: read, write, ls, delete",
        )
