from __future__ import annotations


class MemoryError(Exception):
    pass


class MemoryNotFoundError(MemoryError):
    def __init__(self, msg: str = "Memory entry not found"):
        super().__init__(msg)


class MemoryValidationError(MemoryError):
    def __init__(self, msg: str = "Memory validation failed"):
        super().__init__(msg)


class MemoryStorageError(MemoryError):
    def __init__(self, msg: str = "Memory storage failed"):
        super().__init__(msg)


class MemoryExtractionError(MemoryError):
    def __init__(self, msg: str = "Memory extraction failed"):
        super().__init__(msg)


class MemoryScoringError(MemoryError):
    def __init__(self, msg: str = "Memory scoring failed"):
        super().__init__(msg)


class MemoryLifecycleError(MemoryError):
    def __init__(self, msg: str = "Memory lifecycle operation failed"):
        super().__init__(msg)


class MemorySummarizationError(MemoryError):
    def __init__(self, msg: str = "Memory summarization failed"):
        super().__init__(msg)


class MemoryDuplicateError(MemoryError):
    def __init__(self, msg: str = "Duplicate memory entry"):
        super().__init__(msg)


class MemoryTenantError(MemoryError):
    def __init__(self, msg: str = "Tenant isolation violation"):
        super().__init__(msg)
