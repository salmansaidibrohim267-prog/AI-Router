from __future__ import annotations


class RerankerError(Exception):
    pass


class RerankerModelError(RerankerError):
    def __init__(self, msg: str = "Reranker model error"):
        super().__init__(msg)


class RerankerInputError(RerankerError):
    def __init__(self, msg: str = "Invalid reranker input"):
        super().__init__(msg)


class RerankerTimeoutError(RerankerError):
    def __init__(self, msg: str = "Reranker timeout"):
        super().__init__(msg)


class RerankerCacheError(RerankerError):
    def __init__(self, msg: str = "Reranker cache error"):
        super().__init__(msg)
