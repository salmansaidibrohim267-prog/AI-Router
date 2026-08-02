from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    tool_name: str
    input: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResponse:
    tool_name: str
    success: bool
    output: str = ""
    error: str = ""
    duration_ms: float = 0.0
    tokens_used: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
