from __future__ import annotations


class VectorStoreError(Exception):
    pass


class CollectionNotFoundError(VectorStoreError):
    def __init__(self, name: str):
        super().__init__(f"Collection not found: {name}")


class CollectionAlreadyExistsError(VectorStoreError):
    def __init__(self, name: str):
        super().__init__(f"Collection already exists: {name}")


class VectorDimensionError(VectorStoreError):
    def __init__(self, expected: int, got: int):
        super().__init__(f"Expected {expected} dimensions, got {got}")


class InvalidNamespaceError(VectorStoreError):
    def __init__(self, namespace: str):
        super().__init__(f"Invalid namespace: {namespace}")


class InvalidMetadataError(VectorStoreError):
    def __init__(self, msg: str = "Invalid metadata"):
        super().__init__(msg)


class DuplicateIdError(VectorStoreError):
    def __init__(self, id: str):
        super().__init__(f"Duplicate id: {id}")


class InvalidScoreError(VectorStoreError):
    def __init__(self, score: float):
        super().__init__(f"Invalid score: {score}")
