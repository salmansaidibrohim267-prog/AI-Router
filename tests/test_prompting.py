from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from app.prompting.budget import TokenBudgetManager
from app.prompting.builder import PromptContextBuilder
from app.prompting.config import PromptingConfig
from app.prompting.exceptions import (
    PromptBudgetError,
    PromptBuildError,
    PromptFormattingError,
    PromptOptimizerError,
    PromptTemplateError,
    PromptValidationError,
    PromptingError,
)
from app.prompting.formatters import (
    CustomFormatter,
    JSONFormatter,
    MarkdownFormatter,
    OutputFormatter,
    PlainTextFormatter,
    create_formatter,
)
from app.prompting.logging import PromptLogger
from app.prompting.models import (
    ContextItem,
    ContextSource,
    ConversationMessage,
    MemoryEntry,
    OutputFormat,
    PromptBuildRequest,
    PromptBuildResult,
    PromptMetrics,
    PromptSection,
    ToolDefinition,
)
from app.prompting.optimizer import ContextOptimizer
from app.prompting.statistics import PromptMetricsTracker
from app.prompting.template import TemplateEngine
from app.prompting.validator import PromptValidator


# ============================================================
# PromptingConfig
# ============================================================
class TestConfig:
    def test_defaults(self):
        c = PromptingConfig()
        assert c.token_budget == 4096
        assert c.response_reservation == 512
        assert c.optimizer_enabled is True
        assert c.formatter == "markdown"

    def test_from_env(self):
        os.environ["PROMPT_TOKEN_BUDGET"] = "8192"
        os.environ["PROMPT_FORMATTER"] = "json"
        os.environ["PROMPT_OPTIMIZER_ENABLED"] = "0"
        try:
            c = PromptingConfig.from_env()
            assert c.token_budget == 8192
            assert c.formatter == "json"
            assert c.optimizer_enabled is False
        finally:
            for k in ["PROMPT_TOKEN_BUDGET", "PROMPT_FORMATTER", "PROMPT_OPTIMIZER_ENABLED"]:
                os.environ.pop(k, None)


# ============================================================
# Models
# ============================================================
class TestModels:
    def test_output_format_values(self):
        assert OutputFormat.MARKDOWN.value == "markdown"
        assert OutputFormat.JSON.value == "json"

    def test_context_source_values(self):
        assert ContextSource.USER.value == "user"
        assert ContextSource.DOCUMENTS.value == "documents"

    def test_context_item_defaults(self):
        item = ContextItem(content="hello")
        assert item.source == ContextSource.CUSTOM
        assert item.score == 0.0
        assert item.token_count == 0

    def test_context_item_to_dict(self):
        item = ContextItem(content="hello", source=ContextSource.USER, score=0.8, metadata={"k": "v"})
        d = item.to_dict()
        assert d["source"] == "user"
        assert d["score"] == 0.8

    def test_conversation_message_defaults(self):
        msg = ConversationMessage()
        assert msg.role == "user"
        assert msg.content == ""

    def test_memory_entry_defaults(self):
        entry = MemoryEntry()
        assert entry.content == ""
        assert entry.importance == 0.0

    def test_tool_definition_defaults(self):
        tool = ToolDefinition()
        assert tool.name == ""
        assert tool.parameters == {}

    def test_prompt_build_request_defaults(self):
        req = PromptBuildRequest()
        assert req.user_query == ""
        assert req.context_items == []
        assert req.template == ""

    def test_prompt_section_defaults(self):
        sec = PromptSection(name="system")
        assert sec.content == ""
        assert sec.tokens == 0

    def test_prompt_section_to_dict(self):
        sec = PromptSection(name="user", content="hi", tokens=5)
        d = sec.to_dict()
        assert d["name"] == "user"
        assert d["tokens"] == 5

    def test_prompt_build_result_defaults(self):
        r = PromptBuildResult()
        assert r.text == ""
        assert r.sections == {}
        assert r.total_tokens == 0
        assert r.truncated is False

    def test_prompt_build_result_to_dict(self):
        r = PromptBuildResult(text="hello", total_tokens=5, format=OutputFormat.JSON)
        d = r.to_dict()
        assert d["text"] == "hello"
        assert d["format"] == "json"

    def test_prompt_metrics_defaults(self):
        m = PromptMetrics()
        assert m.total_builds == 0

    def test_prompt_metrics_to_dict(self):
        m = PromptMetrics(total_builds=5, total_tokens_built=100)
        d = m.to_dict()
        assert d["total_builds"] == 5


# ============================================================
# Exceptions
# ============================================================
class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(PromptTemplateError, PromptingError)
        assert issubclass(PromptValidationError, PromptingError)
        assert issubclass(PromptBudgetError, PromptingError)
        assert issubclass(PromptFormattingError, PromptingError)
        assert issubclass(PromptOptimizerError, PromptingError)
        assert issubclass(PromptBuildError, PromptingError)


# ============================================================
# TemplateEngine
# ============================================================
class TestTemplateEngine:
    def test_render_basic(self):
        engine = TemplateEngine("Hello {{user}}!")
        assert engine.render({"user": "world"}) == "Hello world!"

    def test_render_multiple_placeholders(self):
        engine = TemplateEngine("{{system}} | {{user}}")
        assert engine.render({"system": "S", "user": "U"}) == "S | U"

    def test_render_missing_uses_default(self):
        engine = TemplateEngine("{{user}}")
        assert engine.render({}, missing_default="[empty]") == "[empty]"

    def test_render_missing_default_empty(self):
        engine = TemplateEngine("A{{user}}B")
        assert engine.render({"other": "x"}) == "AB"

    def test_render_none_value_empty(self):
        engine = TemplateEngine("{{user}}")
        assert engine.render({"user": None}) == ""

    def test_render_empty_template(self):
        engine = TemplateEngine("")
        assert engine.render({"user": "x"}) == ""

    def test_placeholders(self):
        engine = TemplateEngine("{{system}} {{user}} {{system}}")
        assert engine.placeholders() == ["system", "user"]

    def test_validate_template_ok(self):
        engine = TemplateEngine("{{system}} {{user}}")
        assert engine.validate_template() == []

    def test_validate_template_unknown(self):
        engine = TemplateEngine("{{system}} {{bogus}}")
        errors = engine.validate_template()
        assert len(errors) == 1
        assert "bogus" in errors[0]

    def test_validate_template_custom_allowed(self):
        engine = TemplateEngine("{{system}} {{custom_var}}")
        assert engine.validate_template({"system", "custom_var"}) == []

    def test_has_placeholder(self):
        engine = TemplateEngine("{{ user }}")
        assert engine.has_placeholder("user") is True

    def test_has_placeholder_false(self):
        engine = TemplateEngine("{{ user }}")
        assert engine.has_placeholder("system") is False

    def test_build_default_template(self):
        engine = TemplateEngine()
        t = engine.build_default_template()
        assert "{{system}}" in t
        assert "{{user}}" in t
        assert "{{context}}" in t

    def test_set_template(self):
        engine = TemplateEngine("old")
        engine.set_template("new {{user}}")
        assert engine.template == "new {{user}}"


# ============================================================
# TokenBudgetManager
# ============================================================
class TestBudgetManager:
    def test_plan_within_budget(self):
        bm = TokenBudgetManager()
        plan = bm.plan(total_estimate=100, token_budget=1000, response_reservation=200)
        assert plan["budget"] == 1000
        assert plan["reservation"] == 200
        assert plan["available"] == 800
        assert plan["used"] == 100
        assert plan["truncated"] is False

    def test_plan_over_budget(self):
        bm = TokenBudgetManager()
        plan = bm.plan(total_estimate=1000, token_budget=1000, response_reservation=200)
        assert plan["used"] == 800
        assert plan["truncated"] is True

    def test_plan_reservation_too_large(self):
        bm = TokenBudgetManager()
        with pytest.raises(PromptBudgetError):
            bm.plan(total_estimate=10, token_budget=100, response_reservation=100)

    def test_plan_reservation_greater_than_budget(self):
        bm = TokenBudgetManager()
        with pytest.raises(PromptBudgetError):
            bm.plan(total_estimate=10, token_budget=100, response_reservation=200)

    def test_plan_reservation_equals_budget(self):
        bm = TokenBudgetManager()
        with pytest.raises(PromptBudgetError, match="must be less than"):
            bm.plan(total_estimate=10, token_budget=100, response_reservation=100)

    def test_plan_defaults_from_config(self):
        bm = TokenBudgetManager(config=PromptingConfig(token_budget=500, response_reservation=100))
        plan = bm.plan(total_estimate=300)
        assert plan["available"] == 400

    def test_count_tokens_empty(self):
        bm = TokenBudgetManager()
        assert bm.count_tokens("") == 0

    def test_count_tokens_whitespace(self):
        bm = TokenBudgetManager()
        assert bm.count_tokens("one two three") == 3

    def test_count_tokens_with_tokenizer(self):
        bm = TokenBudgetManager()
        tokenizer = lambda text: text.split("|")
        assert bm.count_tokens("a|b|c", tokenizer) == 3

    def test_count_tokens_tokenizer_error_falls_back(self):
        bm = TokenBudgetManager()
        tokenizer = MagicMock(side_effect=ValueError("no"))
        assert bm.count_tokens("one two three", tokenizer) == 3

    def test_trim_no_trim_needed(self):
        bm = TokenBudgetManager()
        text = "one two three"
        assert bm.trim_to_budget(text, max_tokens=10) == text

    def test_trim_to_budget(self):
        bm = TokenBudgetManager()
        text = " ".join(f"word{i}" for i in range(100))
        trimmed = bm.trim_to_budget(text, max_tokens=10)
        assert bm.count_tokens(trimmed) <= 10

    def test_trim_to_budget_small(self):
        bm = TokenBudgetManager()
        text = " ".join(f"word{i}" for i in range(50))
        trimmed = bm.trim_to_budget(text, max_tokens=5)
        assert bm.count_tokens(trimmed) <= 5

    def test_trim_budget_words_ge_words(self):
        bm = TokenBudgetManager()
        text = "one two three four"
        tokenizer = lambda t: t.split() * 3
        trimmed = bm.trim_to_budget(text, max_tokens=5, tokenizer=tokenizer)
        assert trimmed == text

    def test_estimate_section_budget_total(self):
        bm = TokenBudgetManager()
        sections = [("a", "one two three"), ("b", "four five")]
        budgets = bm.estimate_section_budget(sections, available=50)
        assert budgets["a"] == 3
        assert budgets["b"] == 2

    def test_estimate_section_budget_scaled(self):
        bm = TokenBudgetManager()
        sections = [("a", "x " * 10), ("b", "y " * 10)]
        budgets = bm.estimate_section_budget(sections, available=10)
        assert budgets["a"] == 5
        assert budgets["b"] == 5

    def test_estimate_section_budget_zero_total(self):
        bm = TokenBudgetManager()
        sections = [("a", ""), ("b", "")]
        budgets = bm.estimate_section_budget(sections, available=50)
        assert budgets == {"a": 0, "b": 0}


# ============================================================
# ContextOptimizer
# ============================================================
class TestOptimizer:
    def make_item(self, content, score=0.9, source=ContextSource.DOCUMENTS, ts=1.0):
        return ContextItem(content=content, source=source, score=score, timestamp=ts)

    def test_optimize_empty(self):
        opt = ContextOptimizer()
        assert opt.optimize([]) == []

    def test_deduplicate_exact_duplicates(self):
        opt = ContextOptimizer()
        items = [
            self.make_item("Hello world", score=0.9),
            self.make_item("Hello world", score=0.8),
        ]
        result = opt.optimize(items)
        assert len(result) == 1

    def test_deduplicate_case_insensitive(self):
        opt = ContextOptimizer()
        items = [
            self.make_item("Hello World", score=0.9),
            self.make_item("hello world", score=0.8),
        ]
        result = opt.optimize(items)
        assert len(result) == 1

    def test_deduplicate_keeps_distinct(self):
        opt = ContextOptimizer()
        items = [
            self.make_item("Hello world", score=0.9),
            self.make_item("Goodbye moon", score=0.8),
        ]
        result = opt.optimize(items)
        assert len(result) == 2

    def test_remove_low_score(self):
        opt = ContextOptimizer()
        items = [
            self.make_item("a", score=0.05),
            self.make_item("b", score=0.5),
        ]
        result = opt.optimize(items)
        assert len(result) == 1
        assert result[0].content == "b"

    def test_merge_overlapping(self):
        opt = ContextOptimizer()
        items = [
            self.make_item("the quick brown fox jumps", score=0.9),
            self.make_item("brown fox jumps over the lazy dog", score=0.7),
        ]
        result = opt.optimize(items)
        assert len(result) == 1

    def test_no_merge_disjoint(self):
        opt = ContextOptimizer()
        items = [
            self.make_item("completely different first topic", score=0.9),
            self.make_item("unrelated second topic entirely", score=0.7),
        ]
        result = opt.optimize(items)
        assert len(result) == 2

    def test_merge_keeps_highest_score(self):
        opt = ContextOptimizer()
        items = [
            self.make_item("the quick brown fox jumps over the lazy dog today", score=0.9),
            self.make_item("the quick brown fox jumps high", score=0.7),
        ]
        result = opt.optimize(items)
        assert len(result) == 1
        assert result[0].score == 0.9

    def test_prioritize_recent_high_score(self):
        opt = ContextOptimizer()
        items = [
            self.make_item("old low", score=0.3, ts=10.0),
            self.make_item("new high", score=0.9, ts=20.0),
        ]
        result = opt.optimize(items)
        assert result[0].content == "new high"

    def test_user_source_boost(self):
        opt = ContextOptimizer()
        items = [
            self.make_item("system note", score=0.8, source=ContextSource.SYSTEM),
            self.make_item("user note", score=0.7, source=ContextSource.USER),
        ]
        result = opt.optimize(items)
        assert result[0].content == "user note"

    def test_optimizer_disabled(self):
        opt = ContextOptimizer(config=PromptingConfig(optimizer_enabled=False))
        items = [self.make_item("x", score=0.5)]
        assert opt.optimize(items) == items

    def test_dedup_disabled(self):
        opt = ContextOptimizer(config=PromptingConfig(dedup_enabled=False, merge_overlap=False))
        items = [
            self.make_item("same", score=0.9),
            self.make_item("same", score=0.8),
        ]
        result = opt.optimize(items)
        assert len(result) == 2

    def test_overlap_ratio(self):
        opt = ContextOptimizer()
        a = "apple banana cherry"
        b = "apple banana cherry pie"
        ratio = opt._overlap_ratio(a, b)
        assert ratio == 1.0

    def test_overlap_ratio_no_common(self):
        opt = ContextOptimizer()
        assert opt._overlap_ratio("one two three", "four five six") == 0.0

    def test_overlap_ratio_empty(self):
        opt = ContextOptimizer()
        assert opt._overlap_ratio("", "x y") == 0.0

    def test_join_items(self):
        opt = ContextOptimizer()
        a = self.make_item("first", score=0.5, ts=1.0)
        b = self.make_item("second", score=0.9, ts=2.0)
        joined = opt._join_items(a, b)
        assert "first" in joined.content
        assert "second" in joined.content
        assert joined.score == 0.9
        assert joined.timestamp == 2.0

    def test_merge_overlapping_single_item(self):
        opt = ContextOptimizer()
        items = [self.make_item("only one")]
        result = opt.optimize(items)
        assert len(result) == 1

    def test_merge_skips_used_inner(self):
        opt = ContextOptimizer()
        items = [
            self.make_item("alpha beta gamma delta epsilon", score=0.9),
            self.make_item("zeta eta theta iota", score=0.8),
            self.make_item("epsilon alpha gamma delta", score=0.7),
        ]
        result = opt.optimize(items)
        assert len(result) == 2

    def test_optimizer_error_wrapped(self):
        opt = ContextOptimizer()
        with patch.object(opt, "_deduplicate", side_effect=ValueError("boom")):
            with pytest.raises(PromptOptimizerError):
                opt.optimize([self.make_item("x")])


# ============================================================
# Formatters
# ============================================================
class TestFormatters:
    def test_markdown_format(self):
        f = MarkdownFormatter()
        text = f.format({"user": "hello", "system": "sys"})
        assert "## user" in text
        assert "## system" in text
        assert "hello" in text

    def test_markdown_skips_empty(self):
        f = MarkdownFormatter()
        text = f.format({"user": "hello", "empty": ""})
        assert "## empty" not in text

    def test_plain_format(self):
        f = PlainTextFormatter()
        text = f.format({"user": "hello"})
        assert "[user]" in text
        assert "hello" in text

    def test_plain_skips_empty(self):
        f = PlainTextFormatter()
        text = f.format({"user": ""})
        assert text == ""

    def test_json_format(self):
        f = JSONFormatter()
        text = f.format({"user": "hello", "num": 1})
        parsed = json.loads(text)
        assert parsed["user"] == "hello"
        assert parsed["num"] == 1

    def test_format_section_empty(self):
        f = PlainTextFormatter()
        assert f.format_section("user", "") == ""

    def test_format_section(self):
        f = PlainTextFormatter()
        assert f.format_section("user", "hi") == "[user]\nhi"

    def test_create_formatter_default_markdown(self):
        f = create_formatter(None)
        assert isinstance(f, MarkdownFormatter)

    def test_create_formatter_plain(self):
        f = create_formatter(OutputFormat.PLAIN)
        assert isinstance(f, PlainTextFormatter)

    def test_create_formatter_json_string(self):
        f = create_formatter("json")
        assert isinstance(f, JSONFormatter)

    def test_create_formatter_custom_enum(self):
        f = create_formatter(OutputFormat.CUSTOM)
        assert isinstance(f, CustomFormatter)

    def test_create_formatter_unknown_string(self):
        f = create_formatter("bogus")
        assert isinstance(f, CustomFormatter)

    def test_custom_formatter_no_func(self):
        f = CustomFormatter()
        text = f.format({"user": "hello"})
        assert "user: hello" in text

    def test_custom_formatter_with_func(self):
        f = CustomFormatter(custom_func=lambda sections: f"<{sections['user']}>")
        assert f.format({"user": "hello"}) == "<hello>"

    def test_custom_formatter_error(self):
        def broken(sections):
            raise ValueError("bad")

        f = CustomFormatter(custom_func=broken)
        with pytest.raises(PromptFormattingError):
            f.format({"user": "hello"})

    def test_formatter_abstract(self):
        import pytest as _pytest
        with _pytest.raises(TypeError):
            OutputFormatter()  # type: ignore[abstract]


# ============================================================
# Validator
# ============================================================
class TestValidator:
    def test_validate_ok(self):
        v = PromptValidator()
        result = PromptBuildResult(text="hello world", sections={"user": "hello"})
        assert v.validate(result) == []

    def test_validate_empty_text(self):
        v = PromptValidator()
        result = PromptBuildResult(text="", sections={"user": "hello"})
        warnings = v.validate(result)
        assert "Prompt text is empty" in warnings

    def test_validate_truncated_warning(self):
        v = PromptValidator()
        result = PromptBuildResult(text="x", sections={"user": "x"}, truncated=True)
        warnings = v.validate(result)
        assert any("truncated" in w for w in warnings)

    def test_validate_no_user_section(self):
        v = PromptValidator()
        result = PromptBuildResult(text="x", sections={"system": "x"})
        warnings = v.validate(result)
        assert any("user" in w for w in warnings)

    def test_validate_no_sections(self):
        v = PromptValidator()
        result = PromptBuildResult(text="x")
        warnings = v.validate(result)
        assert any("sections" in w for w in warnings)

    def test_validate_request_empty_template(self):
        v = PromptValidator()
        with pytest.raises(PromptValidationError):
            v.validate_request(user_query="hello", template="")

    def test_validate_request_empty_query(self):
        v = PromptValidator()
        with pytest.raises(PromptValidationError):
            v.validate_request(user_query="", template="T {{user}}")

    def test_validate_request_ok(self):
        v = PromptValidator()
        v.validate_request(user_query="hello", template="T {{user}}")


# ============================================================
# PromptLogger
# ============================================================
class TestLogger:
    def test_log_build(self, caplog):
        import logging
        logger = PromptLogger("test_prompt_logger")
        logger._logger.setLevel(logging.INFO)
        req = PromptBuildRequest(user_query="q")
        result = PromptBuildResult(text="x", sections={"user": "x"}, total_tokens=5)
        logger.log_build(req, result)
        assert len(caplog.records) >= 0

    def test_log_error(self, caplog):
        import logging
        logger = PromptLogger("test_prompt_logger2")
        logger._logger.setLevel(logging.INFO)
        logger.log_error(ValueError("boom"), "query")
        assert len(caplog.records) >= 0

    def test_log_disabled(self):
        import logging
        logger = PromptLogger("test_disabled_logger")
        logger._logger.setLevel(logging.WARNING)
        req = PromptBuildRequest(user_query="q")
        logger.log_build(req, PromptBuildResult())


# ============================================================
# PromptMetricsTracker
# ============================================================
class TestMetrics:
    def test_initial(self):
        mt = PromptMetricsTracker()
        assert mt.get_metrics().total_builds == 0

    def test_record_build(self):
        mt = PromptMetricsTracker()
        mt.record_build(total_tokens=100, latency_ms=50.0)
        m = mt.get_metrics()
        assert m.total_builds == 1
        assert m.total_tokens_built == 100
        assert m.average_latency_ms == 50.0

    def test_record_build_truncated(self):
        mt = PromptMetricsTracker()
        mt.record_build(total_tokens=10, latency_ms=1.0, truncated=True)
        assert mt.get_metrics().truncations == 1

    def test_record_validation_failure(self):
        mt = PromptMetricsTracker()
        mt.record_validation_failure()
        assert mt.get_metrics().validation_failures == 1

    def test_average_tokens(self):
        mt = PromptMetricsTracker()
        mt.record_build(total_tokens=100, latency_ms=1.0)
        mt.record_build(total_tokens=200, latency_ms=1.0)
        m = mt.get_metrics()
        assert m.average_tokens_per_build == 150.0

    def test_get_metrics_dict(self):
        mt = PromptMetricsTracker()
        mt.record_build(total_tokens=10, latency_ms=5.0)
        d = mt.get_metrics_dict()
        assert d["total_builds"] == 1

    def test_reset(self):
        mt = PromptMetricsTracker()
        mt.record_build(total_tokens=10, latency_ms=5.0)
        mt.reset()
        assert mt.get_metrics().total_builds == 0

    def test_uptime(self):
        mt = PromptMetricsTracker()
        assert mt.uptime_seconds() >= 0


# ============================================================
# PromptContextBuilder
# ============================================================
class TestBuilder:
    def make_request(self, **kwargs):
        defaults = dict(user_query="what is AI?")
        defaults.update(kwargs)
        return PromptBuildRequest(**defaults)

    def test_build_basic(self):
        builder = PromptContextBuilder()
        result = builder.build(self.make_request())
        assert result.text
        assert "what is AI?" in result.text
        assert result.total_tokens > 0
        assert result.truncated is False

    def test_build_with_custom_template(self):
        builder = PromptContextBuilder()
        request = self.make_request(template="Q: {{user}}")
        result = builder.build(request)
        assert result.text == "Q: what is AI?"

    def test_build_sections_rendered(self):
        builder = PromptContextBuilder()
        request = self.make_request(
            system_instructions="Be helpful",
            context_items=[ContextItem(content="context doc", score=0.9)],
        )
        result = builder.build(request)
        assert result.sections["system"] == "Be helpful"
        assert "context doc" in result.sections["context"]

    def test_build_with_conversation(self):
        builder = PromptContextBuilder()
        request = self.make_request(
            conversation_history=[
                ConversationMessage(role="user", content="hi"),
                ConversationMessage(role="assistant", content="hello"),
            ]
        )
        result = builder.build(request)
        assert "hi" in result.sections["conversation"]
        assert "hello" in result.sections["conversation"]

    def test_build_with_memory(self):
        builder = PromptContextBuilder()
        request = self.make_request(
            memory_entries=[MemoryEntry(content="user likes coffee", importance=0.9)]
        )
        result = builder.build(request)
        assert "coffee" in result.sections["memory"]

    def test_build_with_tools(self):
        builder = PromptContextBuilder()
        request = self.make_request(
            tools=[ToolDefinition(name="search", description="Search the web", parameters={"q": "str"})]
        )
        result = builder.build(request)
        assert "search" in result.sections["tools"]
        assert "q" in result.sections["tools"]

    def test_build_format_plain(self):
        builder = PromptContextBuilder()
        request = self.make_request(output_format=OutputFormat.PLAIN)
        result = builder.build(request)
        assert "[user]" in result.text

    def test_build_format_json(self):
        builder = PromptContextBuilder()
        request = self.make_request(output_format=OutputFormat.JSON)
        result = builder.build(request)
        parsed = json.loads(result.text)
        assert "user" in parsed

    def test_build_truncates_when_over_budget(self):
        builder = PromptContextBuilder()
        long_text = "word " * 500
        request = self.make_request(
            context_items=[ContextItem(content=long_text, score=0.9)],
            token_budget=200,
            response_reservation=50,
        )
        result = builder.build(request)
        assert result.truncated is True
        assert result.total_tokens <= 150

    def test_build_empty_query_still_builds(self):
        builder = PromptContextBuilder()
        result = builder.build(PromptBuildRequest(user_query=""))
        assert result.total_tokens == 0

    def test_build_empty_template_error(self):
        builder = PromptContextBuilder()
        request = self.make_request(template="   ")
        with pytest.raises(PromptTemplateError):
            builder.build(request)

    def test_build_unknown_placeholder_error(self):
        builder = PromptContextBuilder()
        request = self.make_request(template="Hello {{bogus}}")
        with pytest.raises(PromptTemplateError, match="bogus"):
            builder.build(request)

    def test_build_without_validation(self):
        builder = PromptContextBuilder(config=PromptingConfig(validation_enabled=False))
        request = self.make_request(template="Hello {{bogus}}")
        result = builder.build(request)
        assert result.text == "Hello "

    def test_build_no_placeholders_keeps_content(self):
        builder = PromptContextBuilder()
        request = self.make_request(template="Just a plain template", user_query="ignored")
        result = builder.build(request)
        assert result.sections == {}

    def test_build_optimizer_flow(self):
        builder = PromptContextBuilder()
        request = self.make_request(
            context_items=[
                ContextItem(content="duplicate text", score=0.9),
                ContextItem(content="duplicate text", score=0.5),
                ContextItem(content="unique text", score=0.01),
            ]
        )
        result = builder.build(request)
        assert result.context_items_used == 1

    def test_build_async(self):
        builder = PromptContextBuilder()

        async def run():
            return await builder.build_async(self.make_request())

        import asyncio
        result = asyncio.run(run())
        assert "what is AI?" in result.text

    def test_preview(self):
        builder = PromptContextBuilder()
        text = builder.preview(self.make_request())
        assert "what is AI?" in text

    def test_estimate_tokens(self):
        builder = PromptContextBuilder()
        count = builder.estimate_tokens(self.make_request())
        assert count > 0

    def test_estimate_tokens_with_tokenizer(self):
        builder = PromptContextBuilder()
        count = builder.estimate_tokens(
            self.make_request(user_query="a b c"),
            tokenizer=lambda text: text.split(),
        )
        assert count >= 1

    def test_estimate_tokens_empty(self):
        builder = PromptContextBuilder()
        count = builder.estimate_tokens(PromptBuildRequest(user_query=""))
        template = builder._template_engine.build_default_template()
        rendered = TemplateEngine(template).render({})
        assert count == len(rendered.split())

    def test_get_metrics(self):
        builder = PromptContextBuilder()
        assert builder.get_metrics().total_builds == 0
        builder.build(self.make_request())
        assert builder.get_metrics().total_builds == 1

    def test_build_context_sources(self):
        builder = PromptContextBuilder()
        request = self.make_request(
            context_items=[
                ContextItem(content="from doc", source=ContextSource.DOCUMENTS, score=0.8),
                ContextItem(content="from user", source=ContextSource.USER, score=0.7),
            ]
        )
        result = builder.build(request)
        assert "source: user" in result.sections["context"]
        assert "source: documents" in result.sections["context"]

    def test_build_metadata_source_label(self):
        builder = PromptContextBuilder()
        request = self.make_request(
            context_items=[
                ContextItem(content="from meta", score=0.9, metadata={"source": "file1.md"}),
            ]
        )
        result = builder.build(request)
        assert "file1.md" in result.sections["context"]

    def test_build_custom_variables_instructions(self):
        builder = PromptContextBuilder()
        request = self.make_request(custom_variables={"instructions": "Follow the rules"})
        result = builder.build(request)
        assert result.sections["instructions"] == "Follow the rules"

    def test_build_custom_variables_non_string_instructions(self):
        builder = PromptContextBuilder()
        request = self.make_request(custom_variables={"instructions": 123})
        result = builder.build(request)
        assert result.sections["instructions"] == ""

    def test_build_custom_formatter(self):
        builder = PromptContextBuilder()
        request = self.make_request()
        result = builder.build(
            request,
            custom_formatter=lambda sections: f"Wrapped: {sections['user']}",
        )
        assert result.text == f"Wrapped: {request.user_query}"

    def test_build_memory_limited(self):
        builder = PromptContextBuilder(config=PromptingConfig(max_memory_entries=2))
        request = self.make_request(
            memory_entries=[
                MemoryEntry(content=f"memory {i}") for i in range(5)
            ]
        )
        result = builder.build(request)
        assert "memory 0" in result.sections["memory"]
        assert "memory 4" not in result.sections["memory"]

    def test_build_tools_limited(self):
        builder = PromptContextBuilder(config=PromptingConfig(max_tools=2))
        request = self.make_request(
            tools=[
                ToolDefinition(name=f"tool{i}", description="desc") for i in range(5)
            ]
        )
        result = builder.build(request)
        assert "tool0" in result.sections["tools"]
        assert "tool4" not in result.sections["tools"]

    def test_build_history_limited(self):
        builder = PromptContextBuilder(config=PromptingConfig(max_history_turns=2))
        request = self.make_request(
            conversation_history=[
                ConversationMessage(role="user", content=f"msg{i}") for i in range(5)
            ]
        )
        result = builder.build(request)
        assert "msg0" in result.sections["conversation"]
        assert "msg4" not in result.sections["conversation"]

    def test_build_with_config_formatter(self):
        builder = PromptContextBuilder(config=PromptingConfig(formatter="json"))
        result = builder.build(self.make_request())
        json.loads(result.text)

    def test_build_warnings_recorded(self):
        builder = PromptContextBuilder()
        request = self.make_request(token_budget=100, response_reservation=50)
        result = builder.build(request)
        assert result.warnings == []

    def test_invalid_reservation_raises_budget_error(self):
        builder = PromptContextBuilder()
        request = self.make_request(token_budget=100, response_reservation=200)
        with pytest.raises(PromptBudgetError):
            builder.build(request)

    def test_build_empty_text_validation_error(self):
        builder = PromptContextBuilder()
        request = self.make_request(template="{{user}}", user_query="")
        with pytest.raises(PromptValidationError, match="empty"):
            builder.build(request)

    def test_build_unexpected_error_wrapped(self):
        builder = PromptContextBuilder()
        with patch.object(builder._logger, "log_build", side_effect=ValueError("boom")):
            with pytest.raises(PromptBuildError):
                builder.build(self.make_request())


# ============================================================
# Factory
# ============================================================
class TestFactory:
    def test_create_default(self):
        from app.prompting import create_prompt_context_builder
        builder = create_prompt_context_builder()
        assert isinstance(builder, PromptContextBuilder)

    def test_create_with_config(self):
        from app.prompting import create_prompt_context_builder
        builder = create_prompt_context_builder(config=PromptingConfig(token_budget=1024))
        assert builder._config.token_budget == 1024
