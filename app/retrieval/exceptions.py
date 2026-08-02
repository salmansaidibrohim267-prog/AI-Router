from __future__ import annotations


class RetrievalError(Exception):
    pass


class InvalidQueryError(RetrievalError):
    def __init__(self, msg: str = "Invalid search query"):
        super().__init__(msg)


class EmptyQueryError(InvalidQueryError):
    def __init__(self):
        super().__init__("Query text and vector are both empty")


class VectorDimensionMismatchError(RetrievalError):
    def __init__(self, expected: int, got: int):
        super().__init__(f"Expected {expected} dimensions, got {got}")


class InvalidSimilarityMetricError(RetrievalError):
    def __init__(self, metric: str):
        super().__init__(f"Unknown similarity metric: {metric}")


class PaginationError(RetrievalError):
    def __init__(self, msg: str = "Invalid pagination"):
        super().__init__(msg)


class FilterError(RetrievalError):
    def __init__(self, msg: str = "Invalid filter"):
        super().__init__(msg)


class BM25Error(RetrievalError):
    def __init__(self, msg: str = "BM25 error"):
        super().__init__(msg)


class FusionError(RetrievalError):
    def __init__(self, msg: str = "Fusion error"):
        super().__init__(msg)


class NormalizationError(RetrievalError):
    def __init__(self, msg: str = "Normalization error"):
        super().__init__(msg)


class QueryExpansionError(RetrievalError):
    def __init__(self, msg: str = "Query expansion error"):
        super().__init__(msg)
