from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class PromptingConfig:
    token_budget: int = 4096
    response_reservation: int = 512
    min_context_tokens: int = 128
    default_template: str = ""
    max_history_turns: int = 10
    max_memory_entries: int = 20
    max_tools: int = 10
    optimizer_enabled: bool = True
    dedup_enabled: bool = True
    merge_overlap: bool = True
    min_score_threshold: float = 0.1
    priority_recent: bool = True
    formatter: str = "markdown"
    validation_enabled: bool = True
    log_builds: bool = True
    track_metrics: bool = True
    overlap_ratio: float = 0.6

    @classmethod
    def from_env(cls) -> PromptingConfig:
        return cls(
            token_budget=int(os.getenv("PROMPT_TOKEN_BUDGET", "4096")),
            response_reservation=int(os.getenv("PROMPT_RESPONSE_RESERVATION", "512")),
            min_context_tokens=int(os.getenv("PROMPT_MIN_CONTEXT_TOKENS", "128")),
            default_template=os.getenv("PROMPT_DEFAULT_TEMPLATE", ""),
            max_history_turns=int(os.getenv("PROMPT_MAX_HISTORY_TURNS", "10")),
            max_memory_entries=int(os.getenv("PROMPT_MAX_MEMORY_ENTRIES", "20")),
            max_tools=int(os.getenv("PROMPT_MAX_TOOLS", "10")),
            optimizer_enabled=os.getenv("PROMPT_OPTIMIZER_ENABLED", "1") == "1",
            dedup_enabled=os.getenv("PROMPT_DEDUP_ENABLED", "1") == "1",
            merge_overlap=os.getenv("PROMPT_MERGE_OVERLAP", "1") == "1",
            min_score_threshold=float(os.getenv("PROMPT_MIN_SCORE", "0.1")),
            priority_recent=os.getenv("PROMPT_PRIORITY_RECENT", "1") == "1",
            formatter=os.getenv("PROMPT_FORMATTER", "markdown"),
            validation_enabled=os.getenv("PROMPT_VALIDATION_ENABLED", "1") == "1",
            log_builds=os.getenv("PROMPT_LOG_BUILDS", "1") == "1",
            track_metrics=os.getenv("PROMPT_TRACK_METRICS", "1") == "1",
            overlap_ratio=float(os.getenv("PROMPT_OVERLAP_RATIO", "0.6")),
        )
