from __future__ import annotations

import asyncio
import shlex

from app.tools.base import Tool, ToolCall, ToolResponse, ToolSpec


class ShellTool(Tool):
    spec = ToolSpec(
        name="shell",
        description="Execute a shell command and return the output",
        parameters={
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Shell command to execute"},
            },
            "required": ["input"],
        },
        required_permissions=["shell_exec"],
        timeout=60,
    )

    async def execute(self, call: ToolCall) -> ToolResponse:
        cmd = call.input.strip()
        if not cmd:
            return ToolResponse(
                tool_name=self.spec.name,
                success=False,
                error="No command provided",
            )
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
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
                output=out,
            )
        except asyncio.TimeoutError:
            return ToolResponse(
                tool_name=self.spec.name,
                success=False,
                error="Command timed out",
            )
        except Exception as e:
            return ToolResponse(
                tool_name=self.spec.name,
                success=False,
                error=str(e),
            )
