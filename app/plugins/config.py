from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class PluginConfig:
    plugins_dir: str = "plugins_ext"
    timeout_seconds: float = 30.0
    cpu_limit: float = 1.0
    max_memory_mb: float = 512.0
    fs_allowed_paths: list[str] = field(default_factory=lambda: ["."])
    network_allowed: bool = False
    processes_allowed: bool = False
    signature_secret: str = ""
    require_signatures: bool = False
    auto_enable: bool = True
    max_plugins: int = 100
    log_events: bool = True
    track_metrics: bool = True

    @classmethod
    def from_env(cls) -> PluginConfig:
        return cls(
            plugins_dir=os.getenv("PLG_DIR", "plugins_ext"),
            timeout_seconds=float(os.getenv("PLG_TIMEOUT", "30")),
            cpu_limit=float(os.getenv("PLG_CPU_LIMIT", "1")),
            max_memory_mb=float(os.getenv("PLG_MAX_MEMORY_MB", "512")),
            network_allowed=os.getenv("PLG_NETWORK", "0") == "1",
            processes_allowed=os.getenv("PLG_PROCESSES", "0") == "1",
            signature_secret=os.getenv("PLG_SIGNATURE_SECRET", ""),
            require_signatures=os.getenv("PLG_REQUIRE_SIGNATURES", "0") == "1",
            auto_enable=os.getenv("PLG_AUTO_ENABLE", "1") == "1",
            max_plugins=int(os.getenv("PLG_MAX_PLUGINS", "100")),
            log_events=os.getenv("PLG_LOG_EVENTS", "1") == "1",
            track_metrics=os.getenv("PLG_TRACK_METRICS", "1") == "1",
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "plugins_dir": self.plugins_dir,
            "timeout_seconds": self.timeout_seconds,
            "cpu_limit": self.cpu_limit,
            "max_memory_mb": self.max_memory_mb,
            "network_allowed": self.network_allowed,
            "processes_allowed": self.processes_allowed,
            "require_signatures": self.require_signatures,
            "auto_enable": self.auto_enable,
            "max_plugins": self.max_plugins,
        }
