from __future__ import annotations

import json
import re
from typing import Any, Protocol

from app.knowledge.ingestion.models import LoadedDocument

try:
    from lxml import etree

    HAS_LXML = True
except ImportError:
    HAS_LXML = False


class DocumentParser(Protocol):
    async def parse(self, document: LoadedDocument, **kwargs) -> str: ...


class PlainTextParser:
    async def parse(self, document: LoadedDocument, **kwargs) -> str:
        return document.content.decode(document.encoding, errors="replace")


class MarkdownParser:
    async def parse(self, document: LoadedDocument, **kwargs) -> str:
        raw = document.content.decode(document.encoding, errors="replace")
        return raw


class PDFParser:
    async def parse(self, document: LoadedDocument, **kwargs) -> str:
        raw = document.content
        text_parts: list[str] = []

        text_pattern = re.compile(rb"\((.*?)\)", re.DOTALL)
        stream_pattern = re.compile(rb"stream\s(.*?)\s*endstream", re.DOTALL)

        for match in text_pattern.finditer(raw):
            part = match.group(1)
            try:
                decoded = part.decode("latin-1", errors="replace")
                decoded = re.sub(r"\\(.)", r"\1", decoded)
                text_parts.append(decoded)
            except Exception:
                pass

        for match in stream_pattern.finditer(raw):
            part = match.group(1)
            try:
                import zlib

                try:
                    decompressed = zlib.decompress(part)
                    decoded = decompressed.decode("latin-1", errors="replace")
                    texts = re.findall(r"\((.*?)\)", decoded)
                    for t in texts:
                        t_clean = re.sub(r"\\(.)", r"\1", t)
                        text_parts.append(t_clean)
                except Exception:
                    decoded = part.decode("latin-1", errors="replace")
                    texts = re.findall(r"\((.*?)\)", decoded)
                    for t in texts:
                        t_clean = re.sub(r"\\(.)", r"\1", t)
                        text_parts.append(t_clean)
            except ImportError:
                pass

        result = "\n".join(text_parts)
        result = result.strip()
        if not result:
            result = "[PDF content could not be fully extracted. Install pypdf or pdfminer.six for better PDF support.]"
        return result


class HTMLParser:
    async def parse(self, document: LoadedDocument, **kwargs) -> str:
        raw = document.content.decode(document.encoding, errors="replace")
        if HAS_LXML:
            try:
                root = etree.fromstring(raw.encode("utf-8"), etree.HTMLParser())
                for tag in ("script", "style", "nav", "footer", "header"):
                    for el in root.iter(tag):
                        el.text = None
                texts = root.xpath("//text()")
                lines = []
                for t in texts:
                    stripped = t.strip()
                    if stripped:
                        lines.append(stripped)
                result = "\n".join(lines)
                if result.strip():
                    return result
            except Exception:
                pass

        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"\s+", " ", text).strip()
        return text


class JSONParser:
    async def parse(self, document: LoadedDocument, **kwargs) -> str:
        raw = document.content.decode(document.encoding, errors="replace")
        try:
            data = json.loads(raw)
            return self._json_to_text(data)
        except json.JSONDecodeError:
            return raw

    def _json_to_text(self, data: Any, indent: str = "") -> str:
        parts: list[str] = []
        if isinstance(data, dict):
            for key, value in data.items():
                parts.append(f"{indent}{key}:")
                parts.append(self._json_to_text(value, indent + "  "))
        elif isinstance(data, list):
            for _, item in enumerate(data):
                parts.append(f"{indent}- {self._json_to_text(item, indent + '  ')}")
        elif isinstance(data, bool):
            parts.append(f"{indent}{'true' if data else 'false'}")
        elif data is None:
            parts.append(f"{indent}null")
        else:
            parts.append(f"{indent}{data}")
        return "\n".join(parts)


_PARSER_MAP = {
    ".txt": PlainTextParser,
    ".md": MarkdownParser,
    ".mdx": MarkdownParser,
    ".pdf": PDFParser,
    ".html": HTMLParser,
    ".htm": HTMLParser,
    ".json": JSONParser,
}


def create_parser(extension: str) -> DocumentParser:
    parser_cls = _PARSER_MAP.get(extension.lower())
    if not parser_cls:
        raise ValueError(f"No parser available for extension: {extension}")
    return parser_cls()
