import pytest

from app.memory.store import SQLiteStore
from app.tasks.queue import TaskQueue
from app.tasks.storage import TaskStorage
from app.tasks.status import TaskState


class TestTaskStorage:
    def test_create_and_get(self):
        store = SQLiteStore(":memory:")
        storage = TaskStorage(store)
        task = storage.create("test_type", {"key": "value"})
        task_id = task["task_id"]
        retrieved = storage.get(task_id)
        assert retrieved is not None
        assert retrieved["type"] == "test_type"
        assert retrieved["state"] == TaskState.QUEUED.value

    def test_update(self):
        store = SQLiteStore(":memory:")
        storage = TaskStorage(store)
        task = storage.create("test", {})
        storage.update(task["task_id"], {"state": TaskState.RUNNING.value})
        updated = storage.get(task["task_id"])
        assert updated["state"] == TaskState.RUNNING.value

    def test_delete(self):
        store = SQLiteStore(":memory:")
        storage = TaskStorage(store)
        task = storage.create("test", {})
        storage.delete(task["task_id"])
        assert storage.get(task["task_id"]) is None

    def test_list_tasks(self):
        store = SQLiteStore(":memory:")
        storage = TaskStorage(store)
        storage.create("type_a", {})
        storage.create("type_a", {})
        storage.create("type_b", {})
        tasks = storage.list_tasks()
        assert len(tasks) == 3

    def test_list_filter_by_state(self):
        store = SQLiteStore(":memory:")
        storage = TaskStorage(store)
        t1 = storage.create("test", {})
        storage.update(t1["task_id"], {"state": TaskState.COMPLETED.value})
        storage.create("test", {})
        tasks = storage.list_tasks(state=TaskState.QUEUED.value)
        assert len(tasks) == 1

    def test_get_queue_depth(self):
        store = SQLiteStore(":memory:")
        storage = TaskStorage(store)
        t1 = storage.create("test", {})
        storage.update(t1["task_id"], {"state": TaskState.RUNNING.value})
        storage.create("test", {})
        depth = storage.get_queue_depth()
        assert depth.get(TaskState.RUNNING.value) == 1
        assert depth.get(TaskState.QUEUED.value) == 1

    def test_add_timeline_event(self):
        store = SQLiteStore(":memory:")
        storage = TaskStorage(store)
        task = storage.create("test", {})
        storage.add_timeline_event(task["task_id"], {"event": "test_event"})
        updated = storage.get(task["task_id"])
        assert len(updated["timeline"]) == 1

    def test_clear(self):
        store = SQLiteStore(":memory:")
        storage = TaskStorage(store)
        storage.create("test", {})
        storage.clear()
        assert len(storage.list_tasks()) == 0


class TestTaskQueue:
    def test_create_and_get(self):
        store = SQLiteStore(":memory:")
        storage = TaskStorage(store)
        queue = TaskQueue(storage)
        task = queue.create_task("orchestrate", {"prompt": "hello"})
        assert task["type"] == "orchestrate"

    def test_cancel_queued(self):
        store = SQLiteStore(":memory:")
        storage = TaskStorage(store)
        queue = TaskQueue(storage)
        task = queue.create_task("test", {})
        assert queue.cancel_task(task["task_id"])
        updated = queue.get_task(task["task_id"])
        assert updated["state"] == TaskState.CANCELLED.value

    def test_cancel_completed_fails(self):
        store = SQLiteStore(":memory:")
        storage = TaskStorage(store)
        queue = TaskQueue(storage)
        task = queue.create_task("test", {})
        queue.complete_task(task["task_id"])
        assert not queue.cancel_task(task["task_id"])

    def test_dequeue(self):
        store = SQLiteStore(":memory:")
        storage = TaskStorage(store)
        queue = TaskQueue(storage)
        queue.create_task("test", {})
        dequeued = queue.dequeue()
        assert dequeued is not None
        assert dequeued["state"] == TaskState.RUNNING.value

    def test_fail_with_retry(self):
        store = SQLiteStore(":memory:")
        storage = TaskStorage(store)
        queue = TaskQueue(storage)
        task = queue.create_task("test", {}, max_retries=1)
        queue.fail_task(task["task_id"], "error")
        updated = queue.get_task(task["task_id"])
        assert updated["state"] == TaskState.RETRYING.value

    def test_fail_no_retry(self):
        store = SQLiteStore(":memory:")
        storage = TaskStorage(store)
        queue = TaskQueue(storage)
        task = queue.create_task("test", {}, max_retries=0)
        queue.fail_task(task["task_id"], "fatal")
        updated = queue.get_task(task["task_id"])
        assert updated["state"] == TaskState.FAILED.value

    def test_get_depth(self):
        store = SQLiteStore(":memory:")
        storage = TaskStorage(store)
        queue = TaskQueue(storage)
        depth = queue.get_depth()
        assert isinstance(depth, dict)
