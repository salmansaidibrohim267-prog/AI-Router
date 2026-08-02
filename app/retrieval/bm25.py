from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


class BM25Tokenizer:
    def tokenize(self, text: str) -> list[str]:
        text = text.lower()
        tokens = re.findall(r"\w+(?:'\w+)?", text)
        return [t for t in tokens if len(t) > 1]


class BM25InvertedIndex:
    def __init__(self, tokenizer: BM25Tokenizer | None = None):
        self._tokenizer = tokenizer or BM25Tokenizer()
        self._doc_freq: dict[str, int] = {}
        self._doc_lengths: dict[str, int] = {}
        self._doc_count: int = 0
        self._avg_doc_length: float = 0.0
        self._postings: dict[str, dict[str, int]] = {}
        self._doc_store: dict[str, dict[str, Any]] = {}
        self._k1: float = 1.5
        self._b: float = 0.75

    @property
    def doc_count(self) -> int:
        return self._doc_count

    @property
    def avg_doc_length(self) -> float:
        return self._avg_doc_length

    def index_document(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        tokens = self._tokenizer.tokenize(text)
        term_counts = Counter(tokens)
        doc_length = len(tokens)

        for term, count in term_counts.items():
            if term not in self._postings:
                self._postings[term] = {}
            self._postings[term][doc_id] = count

        was_present = doc_id in self._doc_lengths
        self._doc_lengths[doc_id] = doc_length
        self._doc_store[doc_id] = {"text": text, "metadata": metadata or {}}

        if not was_present:
            self._doc_count += 1

        self._avg_doc_length = (
            sum(self._doc_lengths.values()) / self._doc_count if self._doc_count > 0 else 0.0
        )
        self._recompute_df()

    def remove_document(self, doc_id: str) -> bool:
        if doc_id not in self._doc_lengths:
            return False
        del self._doc_lengths[doc_id]
        self._doc_store.pop(doc_id, None)
        for term in list(self._postings.keys()):
            self._postings[term].pop(doc_id, None)
            if not self._postings[term]:
                del self._postings[term]
        self._doc_count = max(0, self._doc_count - 1)
        self._avg_doc_length = (
            sum(self._doc_lengths.values()) / self._doc_count if self._doc_count > 0 else 0.0
        )
        self._recompute_df()
        return True

    def clear(self) -> None:
        self._doc_freq.clear()
        self._doc_lengths.clear()
        self._doc_count = 0
        self._avg_doc_length = 0.0
        self._postings.clear()
        self._doc_store.clear()

    def _recompute_df(self) -> None:
        self._doc_freq = {}
        for term, postings in self._postings.items():
            self._doc_freq[term] = len(postings)

    def search(
        self,
        query: str,
        top_k: int = 10,
        filter_ids: set[str] | None = None,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        query_tokens = self._tokenizer.tokenize(query)
        if not query_tokens:
            return []

        scores: dict[str, float] = {}
        for term in query_tokens:
            if term not in self._postings:
                continue
            idf = self._compute_idf(term)
            for doc_id, tf in self._postings[term].items():
                if filter_ids is not None and doc_id not in filter_ids:
                    continue
                doc_len = self._doc_lengths.get(doc_id, 0)
                bm25_score = idf * (tf * (self._k1 + 1)) / (
                    tf + self._k1 * (1 - self._b + self._b * doc_len / max(self._avg_doc_length, 1))
                )
                scores[doc_id] = scores.get(doc_id, 0.0) + bm25_score

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            (doc_id, score, self._doc_store.get(doc_id, {}).get("metadata", {}))
            for doc_id, score in ranked
        ]

    def _compute_idf(self, term: str) -> float:
        df = self._doc_freq.get(term, 0)
        if df == 0:
            return 0.0
        return math.log(1 + (self._doc_count - df + 0.5) / (df + 0.5))

    def get_document_text(self, doc_id: str) -> str:
        entry = self._doc_store.get(doc_id, {})
        return entry.get("text", "")

    def get_document_metadata(self, doc_id: str) -> dict[str, Any]:
        entry = self._doc_store.get(doc_id, {})
        return entry.get("metadata", {})

    def statistics(self) -> dict[str, Any]:
        return {
            "doc_count": self._doc_count,
            "avg_doc_length": round(self._avg_doc_length, 2),
            "unique_terms": len(self._postings),
            "k1": self._k1,
            "b": self._b,
        }

    @property
    def store(self) -> dict[str, dict[str, Any]]:
        return dict(self._doc_store)
