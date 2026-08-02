import re

from app.plugin.base import AIPlugin, HookResult


class GuardrailsPlugin(AIPlugin):
    name = "guardrails"
    version = "1.0.0"
    description = "Content guardrails plugin for blocking harmful or sensitive content"

    def __init__(self):
        self._blocked_patterns: list[re.Pattern] = []
        self._sensitive_patterns: list[re.Pattern] = []

    async def initialize(self) -> None:
        self._blocked_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in [
                r"(?i)ignore\s+all\s+(previous|prior)\s+instructions",
                r"(?i)you\s+are\s+(not\s+)?(a\s+)?(an?\s+)?(ai\s+)?(assistant|chatbot)",
                r"(?i)system\s+prompt",
                r"(?i)jailbreak",
                r"(?i)dan\s*(\s+mode|\s+unleashed|~)",
            ]
        ]
        self._sensitive_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in [
                r"(?i)\b(password|secret|api[_-]?key|token|credential)\s*[:=]",
                r"(?i)(\bssn\b|\bsocial\s+security\b|\bcredit\s+card\b)",
            ]
        ]

    async def before_request(self, request, context) -> HookResult:
        messages = getattr(request, "messages", [])
        for msg in messages:
            content = msg.content if hasattr(msg, "content") else (msg.get("content", "") if isinstance(msg, dict) else "")
            content = content or ""
            for pattern in self._blocked_patterns:
                if pattern.search(content):
                    return HookResult(
                        should_cancel=True,
                        cancel_reason=f"Blocked content matched pattern: {pattern.pattern}",
                        metadata={"guardrails": "blocked", "pattern": pattern.pattern},
                    )
            for pattern in self._sensitive_patterns:
                if pattern.search(content):
                    context["_guardrails_sensitive"] = True
                    context["_guardrails_warning"] = f"Sensitive content pattern: {pattern.pattern}"
                    return HookResult(
                        metadata={
                            "guardrails": "warning",
                            "warning": f"Sensitive content pattern: {pattern.pattern}",
                        }
                    )
        return HookResult(metadata={"guardrails": "passed"})

    async def after_response(self, request, response, context) -> HookResult:
        if context.get("_guardrails_sensitive"):
            return HookResult(
                metadata={
                    "guardrails": "sensitive_request",
                    "warning": context.get("_guardrails_warning", ""),
                }
            )
        return HookResult()

    async def shutdown(self) -> None:
        self._blocked_patterns.clear()
        self._sensitive_patterns.clear()
