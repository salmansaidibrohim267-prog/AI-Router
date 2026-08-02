from __future__ import annotations

import re
from typing import Any

from app.rag.config import RAGConfig
from app.rag.models import (
    IntentType,
    LanguageType,
    QueryAnalysis,
)
from app.retrieval.query_expansion import QueryExpander


class QueryProcessor:
    def __init__(
        self,
        config: RAGConfig | None = None,
        query_expander: QueryExpander | None = None,
    ):
        self._config = config or RAGConfig()
        self._query_expander = query_expander or QueryExpander()

    async def process(self, query: str) -> QueryAnalysis:
        analysis = QueryAnalysis(original=query)
        analysis.normalized = self._normalize(query)
        if self._config.enable_language_detection:
            analysis.language = self._detect_language(analysis.normalized)
        if self._config.enable_intent_classification:
            analysis.intent = self._classify_intent(analysis.normalized)
        if self._config.enable_query_expansion:
            expanded = self._query_expander.expand(analysis.normalized)
            analysis.expanded = " ".join(expanded)
        else:
            analysis.expanded = analysis.normalized
        return analysis

    def _normalize(self, text: str) -> str:
        text = text.strip()
        text = re.sub(r"\s+", " ", text)
        return text

    def _detect_language(self, text: str) -> LanguageType:
        if not text:
            return LanguageType.UNKNOWN
        en_stopwords = {"the", "is", "are", "was", "were", "a", "an", "and", "or", "of", "to", "in", "it", "that", "this"}
        fr_stopwords = {"le", "la", "les", "est", "sont", "un", "une", "des", "pour", "dans", "ce", "ces", "avec", "sur"}
        de_stopwords = {"der", "die", "das", "ist", "sind", "ein", "eine", "und", "oder", "von", "zu", "mit", "auf"}
        es_stopwords = {"el", "la", "los", "las", "es", "son", "un", "una", "y", "o", "de", "en", "por", "para"}
        words = set(re.findall(r"\w+", text.lower()))
        lang_scores: dict[LanguageType, int] = {
            LanguageType.EN: len(words & en_stopwords),
            LanguageType.FR: len(words & fr_stopwords),
            LanguageType.DE: len(words & de_stopwords),
            LanguageType.ES: len(words & es_stopwords),
        }
        best = max(lang_scores, key=lang_scores.get)
        return best if lang_scores[best] > 0 else LanguageType.UNKNOWN

    def _classify_intent(self, text: str) -> IntentType:
        if not text:
            return IntentType.UNKNOWN
        question_patterns = [
            r"^(what|who|where|when|why|how|which|whom|whose)\b",
            r"\?$",
            r"\b(?:can|could|would|will|do|does|did|is|are|was|were)\s+\w+",
        ]
        summarize_patterns = [r"\bsummarize\b|\bsummarise\b|\bsummary\b|tl;dr|in short|briefly"]
        classify_patterns = [r"\bclassify\b|\bcategorize\b|\btype of\b|\bkind of\b|\bsort of\b"]
        text_lower = text.lower()
        for p in summarize_patterns:
            if re.search(p, text_lower):
                return IntentType.SUMMARIZATION
        for p in classify_patterns:
            if re.search(p, text_lower):
                return IntentType.CLASSIFICATION
        for p in question_patterns:
            if re.search(p, text_lower):
                return IntentType.QUESTION
        if len(text.split()) > 10:
            return IntentType.GENERATION
        return IntentType.CHAT
