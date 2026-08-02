"""MCP client — server discovery, tool listing, and tool calls.

Run from the repository root:

    PYTHONPATH=. python examples/mcp/main.py
"""

import asyncio
import os

from app.mcp.client import MCPClient
from app.mcp.config import MCPConfig

SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:3000/mcp")
SERVER_TOKEN = os.getenv("MCP_SERVER_TOKEN", "")
TOOL_NAME = os.getenv("MCP_TOOL", "get_weather")


async def main() -> None:
    config = MCPConfig(
        transport="http",
        url=SERVER_URL,
        auth_type="bearer" if SERVER_TOKEN else "none",
        bearer_token=SERVER_TOKEN,
        connect_timeout=10.0,
    )

    client = MCPClient(config=config)
    await client.connect()
    try:
        info = await client.discover()
        print(f"server: {info.server_name} v{info.server_version}  "
              f"protocol: {info.protocol_version}")

        tools = await client.list_tools()
        print(f"\n{len(tools)} tools available:")
        for tool in tools[:5]:
            print(f"  - {tool.name}: {tool.description}")

        print(f"\ncalling tool: {TOOL_NAME}")
        result = await client.call_tool(TOOL_NAME, {"location": "Jakarta"})
        print(result.text)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
