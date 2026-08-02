from __future__ import annotations

import asyncio

from app.tools.base import Tool, ToolCall, ToolResponse, ToolSpec


class GitTool(Tool):
    spec = ToolSpec(
        name="git",
        description="Execute git commands (status, log, diff, etc.)",
        parameters={
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Git command (e.g. 'status', 'log --oneline -5')"},
            },
            "required": ["input"],
        },
        required_permissions=["git"],
        timeout=30,
    )

    async def execute(self, call: ToolCall) -> ToolResponse:
        cmd = call.input.strip()
        if not cmd:
            return ToolResponse(
                tool_name=self.spec.name,
                success=False,
                error="No git command provided",
            )
        full_cmd = f"git {cmd}"
        try:
            proc = await asyncio.create_subprocess_shell(
                full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            out = stdout.decode(errors="replace").strip()
            err = stderr.decode(errors="replace").strip()
            if proc.returncode == 0:
                return ToolResponse(
                    tool_name=self.spec.name,
                    success=True,
                    output=out or "(no output)",
                )
            return ToolResponse(
                tool_name=self.spec.name,
                success=False,
                error=err or out or f"Exit code {proc.returncode}",
            )
        except Exception as e:
            return ToolResponse(
                tool_name=self.spec.name,
                success=False,
                error=str(e),
            )
