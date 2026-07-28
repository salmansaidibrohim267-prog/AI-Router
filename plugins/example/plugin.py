from app.plugin.base import AIPlugin, HookResult


class ExamplePlugin(AIPlugin):
    name = "example"
    version = "1.0.0"
    description = "Example plugin for testing"

    async def initialize(self) -> None:
        pass

    async def before_request(self, request, context) -> HookResult:
        context["example_plugin_ran"] = True
        return HookResult(metadata={"example": "processed"})

    async def after_response(self, request, response, context) -> HookResult:
        return HookResult(metadata={"example_response": "logged"})

    async def on_error(self, request, error, context) -> HookResult:
        return HookResult()

    async def shutdown(self) -> None:
        pass
