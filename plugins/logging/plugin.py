import logging
import time

from app.plugin.base import AIPlugin, HookResult

logger = logging.getLogger("plugin.logging")


class LoggingPlugin(AIPlugin):
    name = "logging"
    version = "1.0.0"
    description = "Structured logging for requests"

    async def initialize(self) -> None:
        logger.info("Logging plugin initialized")

    async def before_request(self, request, context) -> HookResult:
        context["_plugin_logging_start"] = time.time()
        logger.info(
            "Request started: model=%s stream=%s messages=%d",
            getattr(request, "model", "unknown"),
            getattr(request, "stream", False),
            len(getattr(request, "messages", [])),
        )
        return HookResult()

    async def after_response(self, request, response, context) -> HookResult:
        start = context.pop("_plugin_logging_start", time.time())
        elapsed = (time.time() - start) * 1000
        logger.info(
            "Request completed: model=%s latency=%.1fms",
            getattr(request, "model", "unknown"),
            elapsed,
        )
        return HookResult()

    async def on_error(self, request, error, context) -> HookResult:
        logger.error(
            "Request failed: model=%s error=%s",
            getattr(request, "model", "unknown"),
            error,
        )
        return HookResult()

    async def shutdown(self) -> None:
        logger.info("Logging plugin shut down")
