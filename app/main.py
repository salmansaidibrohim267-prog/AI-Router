"""Main entry point for AI Router with graceful shutdown and startup validation."""

import os
import signal
import sys
import time

import uvicorn

from app.api import app
from app.config import config_manager
from app.logger import logger
from app.secrets import get_secret


REQUIRED_ENV_VARS = {
    "config/models.yaml": "YAML configuration file with task definitions",
}

OPTIONAL_ENV_VARS = {
    "HOST": "0.0.0.0",
    "PORT": "8000",
    "LOG_LEVEL": "info",
    "REDIS_URL": None,
}


def _get_build_metadata():
    """Read build metadata from /app/.meta/build.json if available."""
    try:
        import json
        meta_file = os.path.join(os.path.dirname(__file__), ".meta", "build.json")
        if os.path.isfile(meta_file):
            with open(meta_file) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def validate_environment():
    """Validate critical environment variables on startup.

    Fails only when critical configuration is missing.
    Non-critical missing items generate warnings only.
    """
    build_meta = _get_build_metadata()
    version = build_meta.get("version", app.version)
    git_commit = build_meta.get("git_commit", "unknown")
    build_date = build_meta.get("build_date", "unknown")
    python_ver = build_meta.get("python_version", f"{sys.version_info.major}.{sys.version_info.minor}")

    print("=" * 50)
    print(f"  AI Router Gateway v{version}")
    print(f"  Python: {python_ver}  Build: {build_date}  Commit: {git_commit}")
    print("=" * 50)

    # Critical: config must load
    required_config = config_manager.config
    if not required_config:
        print("  FATAL: No valid configuration loaded.", file=sys.stderr)
        print("  Check config/models.yaml", file=sys.stderr)
        sys.exit(1)

    supported_tasks = config_manager.get_supported_tasks()
    if not supported_tasks:
        print("  FATAL: No tasks configured in config/models.yaml", file=sys.stderr)
        sys.exit(1)

    print(f"  Tasks: {', '.join(supported_tasks)}")
    print(f"  Config hash: {config_manager.config_hash}")

    # Check for duplicate provider names across tasks
    provider_configs = config_manager.get_all_provider_configs()
    seen_providers = {}
    for p in provider_configs:
        if p.name.lower() in seen_providers:
            prev_task = seen_providers[p.name.lower()]
            print(f"  WARNING: Provider '{p.name}' appears in multiple tasks (may cause conflicts)")
        else:
            seen_providers[p.name.lower()] = True

    # Provider API keys
    missing_keys = []
    for p in provider_configs:
        if p.api_key_env:
            key = get_secret(p.api_key_env)
            if key:
                masked = key[:4] + "****" if len(key) > 8 else "****"
                print(f"  Provider '{p.name}': key found ({p.api_key_env}={masked})")
            else:
                print(f"  Provider '{p.name}': WARNING — no key set ({p.api_key_env})")
                missing_keys.append(p.name)

    # Warn if all providers are missing keys
    if len(missing_keys) == len(provider_configs):
        print("  WARNING: No API keys found for any provider. Service will start but requests may fail.")

    # Optional env vars
    for var, default in OPTIONAL_ENV_VARS.items():
        val = os.getenv(var)
        if val:
            print(f"  {var}={val}")
        elif default is not None:
            os.environ.setdefault(var, default)
            print(f"  {var}={default} (default)")

    print(f"  Rate limit: {config_manager.get_rate_limit()[0]} req/{config_manager.get_rate_limit()[1]}s")
    print(f"  Cache TTL: {config_manager.get_cache_ttl()}s")
    print(f"  Timeout: {config_manager.get_timeout()}s")
    print(f"  Profiles: {os.getenv('COMPOSE_PROFILES', 'default')}")
    print("=" * 50)


def graceful_shutdown(signum, frame):
    """Handle SIGTERM/SIGINT with a clean shutdown."""
    sig_name = signal.Signals(signum).name
    logger.info("Shutdown signal received", extra={"signal": sig_name})
    print(f"\nReceived {sig_name}, shutting down gracefully...")
    sys.exit(0)


if __name__ == "__main__":
    validate_environment()

    signal.signal(signal.SIGTERM, graceful_shutdown)
    signal.signal(signal.SIGINT, graceful_shutdown)

    uvicorn.run(
        "app.api:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=False,
        log_level=os.getenv("LOG_LEVEL", "info"),
    )
