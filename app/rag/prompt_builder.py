from __future__ import annotations

from typing import Any

from app.rag.config import RAGConfig
from app.rag.exceptions import RAGPromptError
from app.rag.models import ContextAssembly, ConversationTurn, QueryAnalysis


class PromptBuilder:
    def __init__(self, config: RAGConfig | None = None):
        self._config = config or RAGConfig()

    def build(
        self,
        query: str,
        context: ContextAssembly | None = None,
        history: list[ConversationTurn] | None = None,
        system_prompt: str = "",
        query_analysis: QueryAnalysis | None = None,
        template: str | None = None,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []

        system_content = system_prompt or self._config.system_prompt_template
        if not system_content:
            system_content = self._default_system()
        context_text = self._format_context(context) if context and context.chunks else ""
        system_content = system_content.replace("{context}", context_text)
        if query_analysis:
            meta = self._format_metadata(query_analysis)
            system_content = system_content.replace("{metadata}", meta)
        messages.append({"role": "system", "content": system_content})

        if history:
            for turn in history[: self._config.max_history_turns]:
                role = turn.role if turn.role in ("user", "assistant") else "user"
                messages.append({"role": role, "content": turn.content})

        messages.append({"role": "user", "content": query})
        return messages

    def build_with_template(
        self,
        template: str,
        query: str,
        context: ContextAssembly | None = None,
        history: list[ConversationTurn] | None = None,
        query_analysis: QueryAnalysis | None = None,
    ) -> list[dict[str, str]]:
        context_text = ""
        if context and context.chunks:
            context_text = self._format_context(context)

        history_text = ""
        if history:
            lines: list[str] = []
            for turn in history[: self._config.max_history_turns]:
                label = "User" if turn.role == "user" else "Assistant"
                lines.append(f"{label}: {turn.content}")
            history_text = "\n".join(lines)

        meta = ""
        if query_analysis:
            meta = self._format_metadata(query_analysis)

        content = template.replace("{query}", query)
        content = content.replace("{context}", context_text)
        content = content.replace("{history}", history_text)
        content = content.replace("{metadata}", meta)

        return [{"role": "user", "content": content}]

    def _default_system(self) -> str:
        return (
            "You are a helpful AI assistant. Answer the user's question based on the "
            "provided context. If the context does not contain enough information, "
            "say so honestly.\n\nContext:\n{context}\n\n{metadata}"
        )

    def _format_context(self, context: ContextAssembly) -> str:
        sep = self._config.context_chunk_separator
        parts: list[str] = []
        for i, chunk in enumerate(context.chunks, 1):
            source = f" [Source: {chunk.source}]" if chunk.source else ""
            parts.append(f"[{i}]{source}\n{chunk.content}")
        return sep.join(parts)

    def _format_metadata(self, analysis: QueryAnalysis) -> str:
        parts: list[str] = []
        parts.append(f"Language: {analysis.language.value}")
        parts.append(f"Intent: {analysis.intent.value}")
        parts.append(f"Query confidence: {analysis.confidence:.2f}")
        return "\n".join(parts)
