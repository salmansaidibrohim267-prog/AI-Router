from __future__ import annotations

import mimetypes
import os
from typing import Protocol

from app.knowledge.ingestion.models import LoadedDocument


class DocumentLoader(Protocol):
    async def load(self, path: str, **kwargs) -> LoadedDocument: ...

    async def load_bytes(self, data: bytes, filename: str, **kwargs) -> LoadedDocument: ...


class TextLoader:
    async def load(self, path: str, **kwargs) -> LoadedDocument:
        with open(path, "rb") as f:
            data = f.read()
        return await self.load_bytes(data, os.path.basename(path))

    async def load_bytes(self, data: bytes, filename: str, **kwargs) -> LoadedDocument:
        ext = os.path.splitext(filename)[1].lower() or ".txt"
        mime_type, _ = mimetypes.guess_type(filename)
        return LoadedDocument(
            filename=filename,
            extension=ext,
            mime_type=mime_type or "text/plain",
            content=data,
            size=len(data),
            encoding=kwargs.get("encoding", "utf-8"),
        )


class MarkdownLoader:
    async def load(self, path: str, **kwargs) -> LoadedDocument:
        with open(path, "rb") as f:
            data = f.read()
        return await self.load_bytes(data, os.path.basename(path))

    async def load_bytes(self, data: bytes, filename: str, **kwargs) -> LoadedDocument:
        ext = os.path.splitext(filename)[1].lower()
        if ext not in (".md", ".mdx"):
            ext = ".md"
        mime_type, _ = mimetypes.guess_type(f"file{ext}")
        return LoadedDocument(
            filename=filename,
            extension=ext,
            mime_type=mime_type or "text/markdown",
            content=data,
            size=len(data),
            encoding=kwargs.get("encoding", "utf-8"),
        )


class PDFLoader:
    async def load(self, path: str, **kwargs) -> LoadedDocument:
        with open(path, "rb") as f:
            data = f.read()
        return await self.load_bytes(data, os.path.basename(path))

    async def load_bytes(self, data: bytes, filename: str, **kwargs) -> LoadedDocument:
        ext = ".pdf"
        return LoadedDocument(
            filename=filename,
            extension=ext,
            mime_type="application/pdf",
            content=data,
            size=len(data),
        )


class HTMLLoader:
    async def load(self, path: str, **kwargs) -> LoadedDocument:
        with open(path, "rb") as f:
            data = f.read()
        return await self.load_bytes(data, os.path.basename(path))

    async def load_bytes(self, data: bytes, filename: str, **kwargs) -> LoadedDocument:
        ext = os.path.splitext(filename)[1].lower() or ".html"
        mime_type, _ = mimetypes.guess_type(filename)
        return LoadedDocument(
            filename=filename,
            extension=ext,
            mime_type=mime_type or "text/html",
            content=data,
            size=len(data),
            encoding=kwargs.get("encoding", "utf-8"),
        )


class JSONLoader:
    async def load(self, path: str, **kwargs) -> LoadedDocument:
        with open(path, "rb") as f:
            data = f.read()
        return await self.load_bytes(data, os.path.basename(path))

    async def load_bytes(self, data: bytes, filename: str, **kwargs) -> LoadedDocument:
        ext = ".json"
        return LoadedDocument(
            filename=filename,
            extension=ext,
            mime_type="application/json",
            content=data,
            size=len(data),
            encoding=kwargs.get("encoding", "utf-8"),
        )


_LOADER_MAP = {
    ".txt": TextLoader,
    ".md": MarkdownLoader,
    ".mdx": MarkdownLoader,
    ".pdf": PDFLoader,
    ".html": HTMLLoader,
    ".htm": HTMLLoader,
    ".json": JSONLoader,
}


def create_loader(extension: str) -> DocumentLoader:
    loader_cls = _LOADER_MAP.get(extension.lower())
    if not loader_cls:
        raise ValueError(f"No loader available for extension: {extension}")
    return loader_cls()
