from __future__ import annotations

import json
import time
from typing import Any, Callable

from app.prompting.budget import TokenBudgetManager
from app.prompting.config import PromptingConfig
from app.prompting.exceptions import (
    PromptBuildError,
    PromptingError,
    PromptTemplateError,
    PromptValidationError,
)
from app.prompting.formatters import create_formatter
from app.prompting.logging import PromptLogger
from app.prompting.models import (
    ContextItem,
    MemoryEntry,
    OutputFormat,
    PromptBuildRequest,
    PromptBuildResult,
    ToolDefinition,
)
from app.prompting.optimizer import ContextOptimizer
from app.prompting.statistics import PromptMetricsTracker
from app.prompting.template import TemplateEngine
from app.prompting.validator import PromptValidator


class PromptContextBuilder:
    def __init__(
        self,
        config: PromptingConfig | None = None,
        template_engine: TemplateEngine | None = None,
        budget_manager: TokenBudgetManager | None = None,
        optimizer: ContextOptimizer | None = None,
        validator: PromptValidator | None = None,
        logger: PromptLogger | None = None,
        metrics_tracker: PromptMetricsTracker | None = None,
    ):
        self._config = config or PromptingConfig()
        self._template_engine = template_engine or TemplateEngine(self._config.default_template)
        self._budget = budget_manager or TokenBudgetManager(self._config)
        self._optimizer = optimizer or ContextOptimizer(self._config)
        self._validator = validator or PromptValidator(self._config)
        self._logger = logger or PromptLogger()
        self._metrics = metrics_tracker or PromptMetricsTracker()

    def build(
        self,
        request: PromptBuildRequest,
        custom_formatter=None,
    ) -> PromptBuildResult:
        t_start = time.perf_counter()
        result = PromptBuildResult()
        try:
            template = (
                request.template or self._template_engine.template or self._template_engine.build_default_template()
            )
            if not template.strip():
                raise PromptTemplateError("Template must not be empty")

            self._template_engine.set_template(template)
            template_errors = self._template_engine.validate_template()
            if template_errors and self._config.validation_enabled:
                raise PromptTemplateError("; ".join(template_errors))

            context_items = request.context_items
            if self._config.optimizer_enabled:
                context_items = self._optimizer.optimize(context_items)

            all_sections = self._assemble_sections(request, context_items)
            engine = TemplateEngine(template)
            placeholders = engine.placeholders()
            sections = {name: all_sections[name] for name in placeholders if name in all_sections}

            plan = self._budget.plan(
                total_estimate=0,
                token_budget=request.token_budget,
                response_reservation=request.response_reservation,
            )

            token_counts = {name: self._budget.count_tokens(content) for name, content in sections.items()}
            total = sum(token_counts.values())

            result.sections = sections
            result.section_tokens = token_counts
            result.budget_tokens = plan["budget"]
            result.reserved_tokens = plan["reservation"]
            result.available_tokens = plan["available"]
            result.total_tokens = total
            result.context_items_total = len(request.context_items)
            result.context_items_used = len(context_items)

            if total > result.available_tokens:
                result.truncated = True
                section_budgets = self._budget.estimate_section_budget(
                    list(sections.items()),
                    result.available_tokens,
                )
                trimmed: dict[str, str] = {}
                for name, content in sections.items():
                    budget = section_budgets.get(name, 0)
                    trimmed[name] = self._budget.trim_to_budget(content, budget) if budget > 0 else ""
                sections = trimmed
                result.sections = sections
                result.total_tokens = sum(self._budget.count_tokens(c) for c in sections.values())
                result.section_tokens = {name: self._budget.count_tokens(content) for name, content in sections.items()}

            fmt = request.output_format or OutputFormat(self._config.formatter)
            if custom_formatter is not None:
                fmt = OutputFormat.CUSTOM
            formatter = create_formatter(fmt, custom_formatter)
            result.format = fmt

            if custom_formatter is not None:
                result.text = str(custom_formatter(sections))
            elif fmt == OutputFormat.PLAIN or fmt == OutputFormat.JSON:
                result.text = formatter.format(sections)
            elif placeholders:
                result.text = engine.render(sections)
            else:
                result.text = template

            result.used_tokens = self._budget.count_tokens(result.text)

            if self._config.validation_enabled:
                warnings = self._validator.validate(result)
                result.warnings = warnings
                if "Prompt text is empty" in warnings:
                    raise PromptValidationError("Built prompt text is empty")

            result.build_latency_ms = (time.perf_counter() - t_start) * 1000
            self._logger.log_build(request, result)
            if self._config.track_metrics:
                self._metrics.record_build(
                    total_tokens=result.used_tokens,
                    latency_ms=result.build_latency_ms,
                    truncated=result.truncated,
                )
            return result
        except PromptingError:
            raise
        except Exception as e:
            raise PromptBuildError(f"Prompt build failed: {e}") from e

    async def build_async(
        self,
        request: PromptBuildRequest,
        custom_formatter=None,
    ) -> PromptBuildResult:
        return self.build(request, custom_formatter=custom_formatter)

    def preview(
        self,
        request: PromptBuildRequest,
        custom_formatter=None,
    ) -> str:
        return self.build(request, custom_formatter=custom_formatter).text

    def estimate_tokens(
        self,
        request: PromptBuildRequest,
        tokenizer: Callable | None = None,
    ) -> int:
        template = request.template or self._template_engine.template or self._template_engine.build_default_template()
        context_items = request.context_items
        if self._config.optimizer_enabled:
            context_items = self._optimizer.optimize(context_items)
        sections = self._assemble_sections(request, context_items)
        rendered = TemplateEngine(template).render(sections)
        return self._budget.count_tokens(rendered, tokenizer)

    def _assemble_sections(
        self,
        request: PromptBuildRequest,
        context_items: list[ContextItem],
    ) -> dict[str, str]:
        sections: dict[str, str] = {}
        sections["system"] = request.system_instructions or ""
        sections["instructions"] = self._render_instructions(request)
        sections["context"] = self._render_context_items(context_items)
        sections["conversation"] = self._render_conversation(request.conversation_history)
        sections["memory"] = self._render_memory(request.memory_entries)
        sections["tools"] = self._render_tools(request.tools)
        sections["user"] = request.user_query or ""
        return sections

    def _render_instructions(self, request: PromptBuildRequest) -> str:
        value = request.custom_variables.get("instructions", "")
        return value if isinstance(value, str) else ""

    def _render_context_items(self, items: list[ContextItem]) -> str:
        if not items:
            return ""
        parts: list[str] = []
        for i, item in enumerate(items, 1):
            source_label = ""
            if item.metadata and item.metadata.get("source"):
                source_label = f" (source: {item.metadata['source']})"
            elif item.source.value != "custom":
                source_label = f" (source: {item.source.value})"
            parts.append(f"[{i}]{source_label}\n{item.content}")
        return "\n\n".join(parts)

    def _render_conversation(self, history) -> str:
        if not history:
            return ""
        parts: list[str] = []
        for msg in history[: self._config.max_history_turns]:
            label = "User" if getattr(msg, "role", "user") == "user" else "Assistant"
            parts.append(f"{label}: {msg.content}")
        return "\n".join(parts)

    def _render_memory(self, entries: list[MemoryEntry]) -> str:
        if not entries:
            return ""
        return "\n".join(e.content for e in entries[: self._config.max_memory_entries])

    def _render_tools(self, tools: list[ToolDefinition]) -> str:
        if not tools:
            return ""
        parts: list[str] = []
        for tool in tools[: self._config.max_tools]:
            params = json.dumps(tool.parameters, ensure_ascii=False) if tool.parameters else ""
            suffix = f" {params}" if params else ""
            parts.append(f"- {tool.name}: {tool.description}{suffix}")
        return "\n".join(parts)

    def get_metrics(self) -> Any:
        return self._metrics.get_metrics()
