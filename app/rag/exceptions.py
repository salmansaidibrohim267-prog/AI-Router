from __future__ import annotations


class RAGError(Exception):
    pass


class RAGQueryError(RAGError):
    def __init__(self, msg: str = "Invalid RAG query"):
        super().__init__(msg)


class RAGRetrievalError(RAGError):
    def __init__(self, msg: str = "Retrieval failed"):
        super().__init__(msg)


class RAGContextError(RAGError):
    def __init__(self, msg: str = "Context building failed"):
        super().__init__(msg)


class RAGPromptError(RAGError):
    def __init__(self, msg: str = "Prompt building failed"):
        super().__init__(msg)


class RAGGenerationError(RAGError):
    def __init__(self, msg: str = "Generation failed"):
        super().__init__(msg)


class RAGCacheError(RAGError):
    def __init__(self, msg: str = "RAG cache error"):
        super().__init__(msg)


class RAGFallbackTriggered(RAGError):
    def __init__(self, msg: str = "Fallback triggered"):
        super().__init__(msg)
