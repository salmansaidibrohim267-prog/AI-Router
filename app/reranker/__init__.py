from app.reranker.caching import RerankerCache
from app.reranker.calibration import (
    CalibrationStrategy,
    MinMaxCalibration,
    SigmoidCalibration,
    SoftmaxCalibration,
    ZScoreCalibration,
    create_calibration_strategy,
)
from app.reranker.config import RerankerConfig
from app.reranker.exceptions import (
    RerankerCacheError,
    RerankerError,
    RerankerInputError,
    RerankerModelError,
    RerankerTimeoutError,
)
from app.reranker.logging import RerankerLogger
from app.reranker.models import RerankerInput, RerankerMetrics, RerankerResponse, RerankerResult
from app.reranker.pipeline import CandidateSelectionPipeline
from app.reranker.protocol import BaseReranker
from app.reranker.providers import (
    CrossEncoderReranker,
    EnsembleReranker,
    RuleBasedReranker,
)
from app.reranker.statistics import RerankerMetricsTracker

__all__ = [
    "RerankerConfig",
    "RerankerInput",
    "RerankerMetrics",
    "RerankerResult",
    "RerankerResponse",
    "RerankerCacheError",
    "RerankerError",
    "RerankerInputError",
    "RerankerModelError",
    "RerankerTimeoutError",
    "BaseReranker",
    "CalibrationStrategy",
    "MinMaxCalibration",
    "SigmoidCalibration",
    "SoftmaxCalibration",
    "ZScoreCalibration",
    "create_calibration_strategy",
    "RerankerCache",
    "CandidateSelectionPipeline",
    "RerankerLogger",
    "RerankerMetricsTracker",
    "CrossEncoderReranker",
    "EnsembleReranker",
    "RuleBasedReranker",
]


def create_reranker(
    config: RerankerConfig | None = None,
) -> BaseReranker:
    cfg = config or RerankerConfig.from_env()
    calibration = cfg.calibration
    provider = cfg.provider

    if provider == "rule_based":
        return RuleBasedReranker(calibration=calibration)
    elif provider == "cross_encoder":
        return CrossEncoderReranker(
            model_name=cfg.cross_encoder_model,
            batch_size=cfg.batch_size,
            max_length=cfg.max_length,
            calibration=calibration,
        )
    elif provider == "ensemble":
        weights = None
        if cfg.ensemble_weights:
            weights = [float(w) for w in cfg.ensemble_weights.split(",")]
        sub_rerankers: list[BaseReranker] = [
            RuleBasedReranker(),
            CrossEncoderReranker(
                model_name=cfg.cross_encoder_model,
                batch_size=cfg.batch_size,
                max_length=cfg.max_length,
            ),
        ]
        return EnsembleReranker(
            rerankers=sub_rerankers,
            weights=weights,
            calibration=calibration,
        )
    else:
        raise ValueError(f"Unknown reranker provider: {provider}")
