# MCP

Model Context Protocol client: connects to any MCP server (stdio or HTTP),
discovers its capabilities and tools, and calls tools programmatically.

## Run

```bash
# from the repository root
PYTHONPATH=. python examples/mcp/main.py
```

Point `MCP_SERVER_URL` at any MCP-over-HTTP server (see `.env.example`).

## Expected output

```
server: weather-server v1.0.0  protocol: 2025-03-26

3 tools available:
  - get_weather: Current weather for a location
  - get_forecast: 5-day forecast for a location

calling tool: get_weather
It is 31°C and partly cloudy in Jakarta.
```

See `docs/plugins.md` for the MCP integration overview.
