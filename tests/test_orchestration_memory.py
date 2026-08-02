import pytest

from app.orchestration.memory import ExecutionMemory


class TestExecutionMemory:
    def test_set_and_get(self):
        m = ExecutionMemory()
        m.set("key", "value")
        assert m.get("key") == "value"

    def test_get_default(self):
        m = ExecutionMemory()
        assert m.get("nonexistent", "default") == "default"

    def test_get_all(self):
        m = ExecutionMemory()
        m.set("a", 1)
        m.set("b", 2)
        data = m.get_all()
        assert data == {"a": 1, "b": 2}

    def test_update(self):
        m = ExecutionMemory()
        m.update({"x": 10, "y": 20})
        assert m.get("x") == 10
        assert m.get("y") == 20

    def test_contains(self):
        m = ExecutionMemory()
        m.set("present", True)
        assert "present" in m
        assert "missing" not in m

    def test_clear(self):
        m = ExecutionMemory()
        m.set("a", 1)
        m.clear()
        assert len(m) == 0

    def test_len(self):
        m = ExecutionMemory()
        assert len(m) == 0
        m.set("a", 1)
        assert len(m) == 1
        m.set("b", 2)
        assert len(m) == 2

    def test_keys(self):
        m = ExecutionMemory()
        m.set("a", 1)
        m.set("b", 2)
        assert sorted(m.keys()) == ["a", "b"]

    def test_resolve_refs_simple(self):
        m = ExecutionMemory()
        m.set("name", "World")
        result = m.resolve_refs("Hello {{name}}")
        assert result == "Hello World"

    def test_resolve_refs_missing(self):
        m = ExecutionMemory()
        result = m.resolve_refs("Hello {{missing}}")
        assert result == "Hello "

    def test_resolve_refs_multiple(self):
        m = ExecutionMemory()
        m.set("first", "Hello")
        m.set("second", "World")
        result = m.resolve_refs("{{first}} {{second}}")
        assert result == "Hello World"

    def test_resolve_refs_no_refs(self):
        m = ExecutionMemory()
        result = m.resolve_refs("plain text")
        assert result == "plain text"

    def test_resolve_refs_nested(self):
        m = ExecutionMemory()
        m.set("outer", "inner")
        result = m.resolve_refs("start {{outer}} end")
        assert result == "start inner end"
