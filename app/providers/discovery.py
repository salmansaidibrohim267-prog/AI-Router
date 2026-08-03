from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from app.providers.base import BaseProvider


def discover_custom_providers(custom_dir: str = "providers") -> dict[str, type[BaseProvider]]:
    providers: dict[str, type[BaseProvider]] = {}
    custom_path = Path(custom_dir)
    if not custom_path.is_dir():
        return providers

    for entry in sorted(custom_path.iterdir()):
        if entry.suffix == ".py" and entry.name != "__init__.py":
            try:
                module_name = f"_custom_provider_{entry.stem}"
                spec = importlib.util.spec_from_file_location(module_name, entry)
                if not spec or not spec.loader:
                    continue

                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, type) and issubclass(attr, BaseProvider) and attr is not BaseProvider:
                        provider_name = getattr(attr, "name", entry.stem.lower())
                        providers[provider_name] = attr
            except Exception:
                import traceback

                traceback.print_exc()

    return providers
