from __future__ import annotations

import math
from abc import ABC, abstractmethod


class CalibrationStrategy(ABC):
    @abstractmethod
    def calibrate(self, scores: list[float]) -> list[float]: ...

    @property
    @abstractmethod
    def name(self) -> str: ...


class MinMaxCalibration(CalibrationStrategy):
    @property
    def name(self) -> str:
        return "min_max"

    def calibrate(self, scores: list[float]) -> list[float]:
        if not scores:
            return []
        mn = min(scores)
        mx = max(scores)
        if mx == mn:
            return [1.0] * len(scores)
        return [(s - mn) / (mx - mn) for s in scores]


class SoftmaxCalibration(CalibrationStrategy):
    @property
    def name(self) -> str:
        return "softmax"

    def calibrate(self, scores: list[float]) -> list[float]:
        if not scores:
            return []
        shifted = [s - max(scores) for s in scores]
        exp_scores = [math.exp(s) for s in shifted]
        total = sum(exp_scores)
        if total == 0:
            return [1.0 / len(scores)] * len(scores)
        return [e / total for e in exp_scores]


class SigmoidCalibration(CalibrationStrategy):
    @property
    def name(self) -> str:
        return "sigmoid"

    def calibrate(self, scores: list[float]) -> list[float]:
        if not scores:
            return []
        return [1.0 / (1.0 + math.exp(-s)) for s in scores]


class ZScoreCalibration(CalibrationStrategy):
    @property
    def name(self) -> str:
        return "z_score"

    def calibrate(self, scores: list[float]) -> list[float]:
        if not scores:
            return []
        n = len(scores)
        mean = sum(scores) / n
        variance = sum((s - mean) ** 2 for s in scores) / n
        std = math.sqrt(variance) if variance > 0 else 1.0
        normalized = [(s - mean) / std for s in scores]
        mn = min(normalized)
        mx = max(normalized)
        if mx == mn:
            return [0.5] * n
        return [(x - mn) / (mx - mn) for x in normalized]


_CALIBRATION_MAP: dict[str, type[CalibrationStrategy]] = {
    "min_max": MinMaxCalibration,
    "softmax": SoftmaxCalibration,
    "sigmoid": SigmoidCalibration,
    "z_score": ZScoreCalibration,
}


def create_calibration_strategy(name: str) -> CalibrationStrategy:
    cls = _CALIBRATION_MAP.get(name)
    if cls is None:
        raise ValueError(f"Unknown calibration strategy: {name}")
    return cls()
