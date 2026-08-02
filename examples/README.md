# Examples

Production-quality, copy-paste-ready examples built against the real AI Router SDK.

Each example is self-contained, reads its settings from environment variables
(see the included `.env.example`), and prints clear output.

| Example                | What it demonstrates                                              |
| ---------------------- | ----------------------------------------------------------------- |
| `simple-chat/`         | REST request, SDK call, and token streaming through the router    |
| `rag/`                 | RAG pipeline: retrieval, grounding, citations, confidence scores  |
| `providers/`           | Direct provider clients: Ollama, OpenAI, Anthropic, Google        |
| `plugin/`              | Custom plugin with request/response hooks + manifest              |
| `mcp/`                 | MCP client: server discovery, tool listing, tool calls            |

## Running any example

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cd examples/<example-name>
cp .env.example .env
python main.py
```

The `AI_ROUTER_HOME` env var is respected by every example: set it to your
AI Router config directory (`config/`) if you run from a different working
directory, or to a fresh directory to keep runtime state isolated.
