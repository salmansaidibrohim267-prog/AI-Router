from __future__ import annotations

import re


class QueryExpander:
    def __init__(
        self,
        synonyms: dict[str, list[str]] | None = None,
        abbreviations: dict[str, str] | None = None,
    ):
        self._synonyms = synonyms or {}
        self._abbreviations = abbreviations or {}
        self._typo_corrections: dict[str, str] = {}

    def expand(self, query: str) -> list[str]:
        queries = [query]
        expanded = self._expand_synonyms(query)
        if expanded != query:
            queries.append(expanded)
        expanded_abbr = self._expand_abbreviations(query)
        if expanded_abbr != query:
            queries.append(expanded_abbr)
        corrected = self._correct_typos(query)
        if corrected != query:
            queries.append(corrected)
        return list(dict.fromkeys(queries))

    def _expand_synonyms(self, query: str) -> str:
        if not self._synonyms:
            return query
        result = query
        for word, syn_list in self._synonyms.items():
            pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
            if pattern.search(result):
                result = result + " " + " ".join(syn_list)
        return result

    def _expand_abbreviations(self, query: str) -> str:
        if not self._abbreviations:
            return query
        result = query
        for abbr, full in self._abbreviations.items():
            pattern = re.compile(rf"\b{re.escape(abbr)}\b", re.IGNORECASE)
            result = pattern.sub(full, result)
        return result

    def _correct_typos(self, query: str) -> str:
        if not self._typo_corrections:
            return query
        result = query
        for typo, correction in self._typo_corrections.items():
            pattern = re.compile(rf"\b{re.escape(typo)}\b", re.IGNORECASE)
            result = pattern.sub(correction, result)
        return result

    def add_synonyms(self, word: str, synonyms: list[str]) -> None:
        if word not in self._synonyms:
            self._synonyms[word] = []
        for s in synonyms:
            if s not in self._synonyms[word]:
                self._synonyms[word].append(s)

    def add_abbreviation(self, abbr: str, full: str) -> None:
        self._abbreviations[abbr] = full

    def add_typo_correction(self, typo: str, correction: str) -> None:
        self._typo_corrections[typo] = correction
