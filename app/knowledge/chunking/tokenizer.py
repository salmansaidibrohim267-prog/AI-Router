from __future__ import annotations

import math
from typing import Protocol


class TokenEstimator(Protocol):
    def estimate(self, text: str) -> int:
        ...


class HeuristicTokenEstimator:
    def estimate(self, text: str) -> int:
        if not text:
            return 0
        char_count = len(text)
        ascii_chars = sum(1 for c in text if ord(c) < 128)
        non_ascii_chars = char_count - ascii_chars
        estimated = math.ceil(ascii_chars / 4) + math.ceil(non_ascii_chars / 2)
        return max(1, estimated)
