from __future__ import annotations

import json
from abc import ABC, abstractmethod

from app.prompting.exceptions import PromptFormattingError
from app.prompting.models import OutputFormat


class OutputFormatter(ABC):
    name: str = "base"

    @abstractmethod
    def format(self, sections: dict[str, str]) -> str:
        pass

    def format_section(self, name: str, content: str) -> str:
        if not content:
            return ""
        return f"[{name}]\n{content}"


class MarkdownFormatter(OutputFormatter):
    name = "markdown"

    def format(self, sections: dict[str, str]) -> str:
        parts: list[str] = []
        for name, content in sections.items():
            if not content:
                continue
            parts.append(f"## {name}\n\n{content}")
        return "\n\n".join(parts)


class PlainTextFormatter(OutputFormatter):
    name = "plain"

    def format(self, sections: dict[str, str]) -> str:
        parts: list[str] = []
        for name, content in sections.items():
            if not content:
                continue
            parts.append(self.format_section(name, content))
        return "\n\n".join(parts)


class JSONFormatter(OutputFormatter):
    name = "json"

    def format(self, sections: dict[str, str]) -> str:
        return json.dumps(sections, ensure_ascii=False, indent=2)


class CustomFormatter(OutputFormatter):
    name = "custom"

    def __init__(self, custom_func=None):
        self._custom_func = custom_func

    def format(self, sections: dict[str, str]) -> str:
        if self._custom_func is None:
            return "\n".join(f"{name}: {content}" for name, content in sections.items() if content)
        try:
            return str(self._custom_func(sections))
        except Exception as e:
            raise PromptFormattingError(f"Custom formatter failed: {e}") from e


def create_formatter(
    output_format: OutputFormat | str | None,
    custom_func=None,
) -> OutputFormatter:
    fmt = output_format or OutputFormat.MARKDOWN
    if isinstance(fmt, str):
        try:
            fmt = OutputFormat(fmt)
        except ValueError:
            return CustomFormatter(custom_func)
    if fmt == OutputFormat.MARKDOWN:
        return MarkdownFormatter()
    if fmt == OutputFormat.PLAIN:
        return PlainTextFormatter()
    if fmt == OutputFormat.JSON:
        return JSONFormatter()
    return CustomFormatter(custom_func)
