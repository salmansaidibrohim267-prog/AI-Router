"""Secrets management with Docker Secrets and environment variable fallback."""

import os
from pathlib import Path

SECRETS_DIR = Path("/run/secrets")


def get_secret(name: str, default: str | None = None) -> str | None:
    """Get secret value from Docker Secrets or environment variable.

    Checks /run/secrets/<name> first (Docker Secrets),
    falls back to os.getenv(name), then returns default.
    """
    secret_path = SECRETS_DIR / name.lower()
    if secret_path.is_file():
        try:
            return secret_path.read_text().strip()
        except OSError:
            pass
    return os.getenv(name, default)
