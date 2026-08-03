from __future__ import annotations

from ..models import EvaluationSample, MetricScore
from ..registry import BaseEvaluator
from .rag import _sentences, _token_overlap


class CitationEvaluator(BaseEvaluator):
    kind = "citation"

    def evaluate_scores(self, sample: EvaluationSample) -> list[MetricScore]:
        text = sample.actual.get("text", "")
        citations = sample.actual.get("citations", [])
        sources = sample.actual.get("sources", [])
        source_ids = {str(s.get("id", s.get("source_id", ""))) for s in sources}
        source_by_id = {str(s.get("id", s.get("source_id", ""))): s.get("content", "") for s in sources}
        sentences = _sentences(text)
        if not sentences:
            return [
                MetricScore("citation_precision", 1.0),
                MetricScore("citation_recall", 1.0),
                MetricScore("citation_verifiability", 1.0),
                MetricScore("citation_density", 0.0),
            ]
        cited_sentences = 0
        verified = 0
        supported = 0
        total_citations = 0
        for sentence in sentences:
            has_citation = False
            for citation in citations:
                ref_id = str(citation.get("source_id", citation.get("id", citation.get("ref", ""))))
                marker = citation.get("index")
                claim = str(citation.get("claim", citation.get("text", sentence)))
                in_sentence = ref_id in sentence or (marker is not None and f"[{marker}]" in sentence)
                if in_sentence:
                    has_citation = True
                    total_citations += 1
                    if ref_id in source_ids:
                        verified += 1
                        source_content = source_by_id.get(ref_id, "")
                        if _token_overlap(claim, source_content) >= self._config.token_overlap_threshold:
                            supported += 1
            if has_citation:
                cited_sentences += 1
        recall = round(cited_sentences / len(sentences), 4)
        verifiability = round(verified / total_citations, 4) if total_citations else 1.0
        precision = round(supported / total_citations, 4) if total_citations else 1.0
        density = round(total_citations / len(sentences), 4)
        return [
            MetricScore("citation_precision", precision),
            MetricScore("citation_recall", recall),
            MetricScore("citation_verifiability", verifiability),
            MetricScore("citation_density", density),
        ]
