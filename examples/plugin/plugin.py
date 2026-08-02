"""Custom plugin example — request/response hooks with a manifest.

AI Router discovers plugins automatically from the `plugins/` directory at
the repository root. Each plugin lives in its own subdirectory and needs two
files: `plugin.py` (the implementation) and `manifest.yaml` (metadata).

To use this example:

    mkdir -p plugins/request-logger
    cp examples/plugin/plugin.py examples/plugin/manifest.yaml plugins/request-logger/
    PYTHONPATH=. python examples/plugin/main.py

The plugin hooks run inside the router pipeline; you will see its log lines
around each request.
"""

from app.plugin.base import AIPlugin, HookResult


class RequestLoggerPlugin(AIPlugin):
    name = "request-logger"
    version = "1.0.0"
    description = "Logs every request entering and leaving the router"

    async def initialize(self) -> None:
        print(f"[plugin:{self.name}] initialized")

    async def before_request(self, request, context) -> HookResult:
        prompt = request.messages[-1].content if request.messages else ""
        print(f"[plugin:{self.name}] before_request: {len(prompt)} chars")
        context["logged_at"] = True
        return HookResult()

    async def before_provider(self, request, provider_name, model, context) -> HookResult:
        print(f"[plugin:{self.name}] routing -> {provider_name}/{model}")
        return HookResult()

    async def after_response(self, request, response, context) -> HookResult:
        text = response.choices[0].message.content if response.choices else ""
        print(f"[plugin:{self.name}] after_response: {len(text)} chars")
        return HookResult(metadata={"response_len": len(text)})

    async def on_error(self, request, error, context) -> HookResult:
        print(f"[plugin:{self.name}] error: {error}")
        return HookResult()

    async def shutdown(self) -> None:
        print(f"[plugin:{self.name}] shutdown")
