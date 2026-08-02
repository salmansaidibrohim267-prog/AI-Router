from __future__ import annotations


class EvaluationError(Exception):
    pass


class EvaluatorNotFoundError(EvaluationError):
    def __init__(self, name: str):
        super().__init__(f"Evaluator {name!r} is not registered")
        self.name = name


class DatasetNotFoundError(EvaluationError):
    def __init__(self, name: str):
        super().__init__(f"Benchmark dataset {name!r} is not registered")
        self.name = name


class BenchmarkRunError(EvaluationError):
    pass


class ReportGenerationError(EvaluationError):
    pass


class QualityGateError(EvaluationError):
    pass


class ComparisonError(EvaluationError):
    pass
