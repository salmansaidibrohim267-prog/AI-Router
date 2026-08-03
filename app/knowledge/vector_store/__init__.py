from app.knowledge.vector_store.config import VectorStoreConfig
from app.knowledge.vector_store.exceptions import (
    CollectionAlreadyExistsError,
    CollectionNotFoundError,
    DuplicateIdError,
    InvalidMetadataError,
    InvalidNamespaceError,
    InvalidScoreError,
    VectorDimensionError,
    VectorStoreError,
)
from app.knowledge.vector_store.models import (
    DeleteRequest,
    DistanceMetric,
    SearchRequest,
    SearchResult,
    UpsertRequest,
    VectorCollection,
    VectorRecord,
    VectorStoreStats,
)
from app.knowledge.vector_store.protocol import VectorStore
from app.knowledge.vector_store.providers import (
    ChromaVectorStore,
    InMemoryVectorStore,
    PgVectorStore,
    QdrantVectorStore,
    RedisVectorStore,
)
from app.knowledge.vector_store.service import VectorStoreService
from app.knowledge.vector_store.statistics import VectorStoreStatistics
from app.knowledge.vector_store.validation import VectorStoreValidator

__all__ = [
    "VectorStoreConfig",
    "DeleteRequest",
    "DistanceMetric",
    "SearchRequest",
    "SearchResult",
    "UpsertRequest",
    "VectorCollection",
    "VectorRecord",
    "VectorStoreStats",
    "CollectionAlreadyExistsError",
    "CollectionNotFoundError",
    "DuplicateIdError",
    "InvalidMetadataError",
    "InvalidNamespaceError",
    "InvalidScoreError",
    "VectorDimensionError",
    "VectorStoreError",
    "VectorStore",
    "VectorStoreValidator",
    "VectorStoreStatistics",
    "VectorStoreService",
    "InMemoryVectorStore",
    "QdrantVectorStore",
    "ChromaVectorStore",
    "PgVectorStore",
    "RedisVectorStore",
]


def create_vector_store(
    config: VectorStoreConfig | None = None,
) -> InMemoryVectorStore | QdrantVectorStore | ChromaVectorStore | PgVectorStore | RedisVectorStore:
    cfg = config or VectorStoreConfig.from_env()
    validator = VectorStoreValidator(dimensions=cfg.dimensions)
    stats = VectorStoreStatistics()
    stats.set_dimensions(cfg.dimensions)
    store: InMemoryVectorStore | QdrantVectorStore | ChromaVectorStore | PgVectorStore | RedisVectorStore
    if cfg.backend == "qdrant":
        store = QdrantVectorStore(
            url=cfg.qdrant_url,
            api_key=cfg.qdrant_api_key,
            prefer_grpc=cfg.qdrant_prefer_grpc,
            dimensions=cfg.dimensions,
            distance=DistanceMetric(cfg.distance),
            validator=validator,
            statistics=stats,
        )
    elif cfg.backend == "chroma":
        store = ChromaVectorStore(
            host=cfg.chroma_host,
            port=cfg.chroma_port,
            auth=cfg.chroma_auth,
            dimensions=cfg.dimensions,
            distance=DistanceMetric(cfg.distance),
            validator=validator,
            statistics=stats,
        )
    elif cfg.backend == "pgvector":
        store = PgVectorStore(
            dsn=cfg.pgvector_dsn,
            table=cfg.pgvector_table,
            pool_size=cfg.pgvector_pool_size,
            dimensions=cfg.dimensions,
            distance=DistanceMetric(cfg.distance),
            validator=validator,
            statistics=stats,
        )
    elif cfg.backend == "redis_vector":
        store = RedisVectorStore(
            redis_url=cfg.redis_url,
            index=cfg.redis_index,
            prefix=cfg.redis_prefix,
            dimensions=cfg.dimensions,
            distance=DistanceMetric(cfg.distance),
            validator=validator,
            statistics=stats,
        )
    else:
        store = InMemoryVectorStore(
            dimensions=cfg.dimensions,
            distance=DistanceMetric(cfg.distance),
            validator=validator,
            statistics=stats,
        )
    stats.set_provider(store.provider_name)
    return store
