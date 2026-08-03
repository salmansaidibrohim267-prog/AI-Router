from __future__ import annotations

import re
from typing import Any

PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
DEFAULT_PLACEHOLDERS = {
    "system",
    "instructions",
    "context",
    "conversation",
    "memory",
    "tools",
    "user",
}


class TemplateEngine:
    def __init__(self, template: str = ""):
        self._template = template

    @property
    def template(self) -> str:
        return self._template

    def set_template(self, template: str) -> None:
        self._template = template

    def render(
        self,
        values: dict[str, Any] | None = None,
        missing_default: str = "",
    ) -> str:
        values = values or {}
        template = self._template
        if not template:
            return template

        def _replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in values:
                return missing_default
            value = values[name]
            return "" if value is None else str(value)

        return PLACEHOLDER_PATTERN.sub(_replace, template)

    def placeholders(self) -> list[str]:
        return list(dict.fromkeys(PLACEHOLDER_PATTERN.findall(self._template)))

    def validate_template(self, allowed: set[str] | None = None) -> list[str]:
        allowed = allowed or DEFAULT_PLACEHOLDERS
        errors: list[str] = []
        for ph in self.placeholders():
            if ph not in allowed:
                errors.append(f"Unknown placeholder: {ph}")
        return errors

    def has_placeholder(self, name: str) -> bool:
        return (
            f"{{{{ {name} }}}}" in self._template
            or f"{{{{ {name}}}}}" in self._template
            or f"{{{{{name}}}}}" in self._template
        )  # noqa: E501

    def build_default_template(self) -> str:
        return (
            "{{system}}\n\n"
            "{{instructions}}\n\n"
            "Context:\n{{context}}\n\n"
            "Conversation history:\n{{conversation}}\n\n"
            "Memory:\n{{memory}}\n\n"
            "Available tools:\n{{tools}}\n\n"
            "User: {{user}}"
        )
