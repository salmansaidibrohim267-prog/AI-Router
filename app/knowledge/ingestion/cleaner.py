from __future__ import annotations

import re
import unicodedata


class TextCleaner:
    def __init__(self, remove_control_chars: bool = True, normalize_unicode: bool = True):
        self._remove_control_chars = remove_control_chars
        self._normalize_unicode = normalize_unicode

    async def clean(self, text: str) -> str:
        text = self._remove_bom(text)
        text = self._normalize_newlines(text)
        text = self._trim_lines(text)
        text = self._normalize_tabs(text)
        if self._normalize_unicode:
            text = self._normalize_unicode_text(text)
        if self._remove_control_chars:
            text = self._strip_control_chars(text)
        text = text.strip()
        return text

    def _remove_bom(self, text: str) -> str:
        for bom in ("\ufeff", "\ufffe"):
            text = text.replace(bom, "")
        return text

    def _normalize_newlines(self, text: str) -> str:
        text = text.replace("\r\n", "\n")
        text = text.replace("\r", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    def _trim_lines(self, text: str) -> str:
        lines = text.split("\n")
        trimmed = [line.strip() for line in lines]
        return "\n".join(trimmed)

    def _normalize_tabs(self, text: str) -> str:
        return text.replace("\t", " ")

    def _normalize_unicode_text(self, text: str) -> str:
        return unicodedata.normalize("NFKC", text)

    def _strip_control_chars(self, text: str) -> str:
        result: list[str] = []
        for ch in text:
            if ch == "\n":
                result.append(ch)
                continue
            cat = unicodedata.category(ch)
            if cat.startswith("C") and cat != "Cf":
                continue
            result.append(ch)
        return "".join(result)
