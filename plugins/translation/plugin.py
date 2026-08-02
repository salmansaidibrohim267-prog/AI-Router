from app.plugin.base import AIPlugin, HookResult


class TranslationPlugin(AIPlugin):
    name = "translation"
    version = "1.0.0"
    description = "Request/response translation plugin for multi-language support"

    def __init__(self):
        self._target_language = ""
        self._source_language = ""

    async def initialize(self) -> None:
        self._target_language = ""
        self._source_language = ""

    async def before_request(self, request, context) -> HookResult:
        metadata = getattr(request, "metadata", {}) or {}
        if isinstance(metadata, dict):
            lang = metadata.get("target_language", "")
            if lang:
                self._target_language = lang
                context["_translation_target"] = lang
                context["_translation_source"] = metadata.get("source_language", "auto")
                return HookResult(
                    metadata={
                        "translation": "request_target_set",
                        "target_language": lang,
                    }
                )
        return HookResult()

    async def after_response(self, request, response, context) -> HookResult:
        target = context.pop("_translation_target", None)
        if target and response:
            return HookResult(
                modified_response=response,
                metadata={
                    "translation": "response_marked",
                    "target_language": target,
                },
            )
        return HookResult()

    async def on_error(self, request, error, context) -> HookResult:
        lang = context.get("_translation_target", "unknown")
        return HookResult(
            metadata={
                "translation_error": str(error),
                "target_language": lang,
            }
        )

    async def shutdown(self) -> None:
        self._target_language = ""
        self._source_language = ""
