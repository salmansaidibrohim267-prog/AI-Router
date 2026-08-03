from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from .exceptions import PluginSignatureError
from .models import Signature


def canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _unsigned(payload: dict[str, Any]) -> dict[str, Any]:
    if "signature" in payload:
        return {key: value for key, value in payload.items() if key != "signature"}
    return payload


def compute_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sign_payload(payload: dict[str, Any], secret: str) -> Signature:
    digest = hmac.new(secret.encode("utf-8"), canonical_json(_unsigned(payload)), hashlib.sha256).hexdigest()
    return Signature(digest=digest)


def verify_payload(payload: dict[str, Any], signature: Signature | str, secret: str) -> bool:
    if not secret:
        return False
    digest = signature.digest if isinstance(signature, Signature) else signature
    if not digest:
        return False
    expected = hmac.new(secret.encode("utf-8"), canonical_json(_unsigned(payload)), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, digest)


def verify_or_raise(payload: dict[str, Any], signature: Signature | str, secret: str, name: str = "") -> None:
    if not verify_payload(payload, signature, secret):
        raise PluginSignatureError(f"signature verification failed for {name or 'plugin'}", name=name)


def hash_directory(root: str) -> str:
    """Content hash of a directory tree (stable, sorted paths)."""
    from pathlib import Path

    digest = hashlib.sha256()
    base = Path(root)
    if not base.is_dir():
        return ""
    for path in sorted(base.rglob("*")):
        if path.is_file():
            rel = str(path.relative_to(base))
            digest.update(rel.encode("utf-8"))
            with open(path, "rb") as fh:
                digest.update(fh.read())
    return digest.hexdigest()
