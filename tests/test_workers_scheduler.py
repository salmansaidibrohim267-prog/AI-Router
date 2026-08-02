import pytest

from app.orchestration.worker_pool import WorkerPool
from app.orchestration.persistence import PersistenceManager, create_store
from app.tasks.scheduler import TaskScheduler
from app.memory.store import SQLiteStore


class TestPersistenceManager:
    def test_create_default(self):
        pm = PersistenceManager(SQLiteStore(":memory:"))
        assert pm.store is not None
        stats = pm.get_stats()
        assert "backend" in stats
        assert "total_keys" in stats

    def test_create_store_sqlite(self):
        store = create_store("sqlite", ":memory:")
        assert store is not None

    def test_store_roundtrip(self):
        pm = PersistenceManager(SQLiteStore(":memory:"))
        pm.store.set("test_key", {"data": 42})
        assert pm.store.get("test_key") == {"data": 42}


class TestTaskScheduler:
    @pytest.mark.asyncio
    async def test_add_job(self):
        store = SQLiteStore(":memory:")
        from app.tasks.storage import TaskStorage
        from app.tasks.queue import TaskQueue
        storage = TaskStorage(store)
        queue = TaskQueue(storage)
        scheduler = TaskScheduler(queue)
        scheduler.add_job("job1", "test", {}, interval=3600)
        assert len(scheduler.list_jobs()) == 1

    def test_remove_job(self):
        store = SQLiteStore(":memory:")
        from app.tasks.storage import TaskStorage
        from app.tasks.queue import TaskQueue
        storage = TaskStorage(store)
        queue = TaskQueue(storage)
        scheduler = TaskScheduler(queue)
        scheduler.add_job("job1", "test", {}, interval=3600)
        scheduler.remove_job("job1")
        assert len(scheduler.list_jobs()) == 0


class TestWorkerPool:
    def test_create_pool(self):
        store = SQLiteStore(":memory:")
        from app.tasks.storage import TaskStorage
        from app.tasks.queue import TaskQueue
        storage = TaskStorage(store)
        queue = TaskQueue(storage)
        pool = WorkerPool(queue, None, worker_count=3)
        status = pool.get_status()
        assert status["worker_count"] == 3
        assert status["workers_initialized"] == 0

    def test_scale(self):
        store = SQLiteStore(":memory:")
        from app.tasks.storage import TaskStorage
        from app.tasks.queue import TaskQueue
        storage = TaskStorage(store)
        queue = TaskQueue(storage)
        pool = WorkerPool(queue, None)
        pool.scale(5)
        status = pool.get_status()
        assert status["worker_count"] == 5
