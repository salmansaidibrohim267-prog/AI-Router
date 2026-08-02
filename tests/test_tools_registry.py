import pytest

from app.tools.base import Tool, ToolSpec, ToolCall, ToolResult
from app.tools.registry import ToolRegistry
from app.tools.executor import ToolExecutor
from app.tools.permission import PermissionManager, PermissionRule
from app.tools.models import ToolCall as ToolCallModel, ToolResponse
from app.tools.builtins.calculator_tool import CalculatorTool
from app.tools.builtins.search_tool import SearchTool
from app.tools.builtins.python_tool import PythonTool
from app.tools.builtins.filesystem_tool import FilesystemTool


class TestToolRegistry:
    def test_register_and_get(self):
        registry = ToolRegistry()
        tool = CalculatorTool()
        registry.register(tool)
        assert registry.get("calculator") is tool

    def test_unregister(self):
        registry = ToolRegistry()
        registry.register(CalculatorTool())
        registry.unregister("calculator")
        assert registry.get("calculator") is None

    def test_list_specs(self):
        registry = ToolRegistry()
        registry.register(CalculatorTool())
        registry.register(SearchTool())
        specs = registry.list_specs()
        assert len(specs) == 2
        names = [s.name for s in specs]
        assert "calculator" in names
        assert "search" in names

    def test_clear(self):
        registry = ToolRegistry()
        registry.register(CalculatorTool())
        registry.clear()
        assert registry.get("calculator") is None


class TestToolExecutor:
    @pytest.mark.asyncio
    async def test_execute_calculator(self):
        registry = ToolRegistry()
        registry.register(CalculatorTool())
        executor = ToolExecutor(registry)
        result = await executor.execute("calculator", "2 + 2")
        assert result.success
        assert result.output == "4"

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        executor = ToolExecutor(ToolRegistry())
        result = await executor.execute("nonexistent", "input")
        assert not result.success
        assert "Unknown" in result.error

    @pytest.mark.asyncio
    async def test_permission_denied(self):
        registry = ToolRegistry()
        registry.register(CalculatorTool())
        permission = PermissionManager()
        permission.grant("calculator", PermissionRule(allowed_users=["admin"]))
        executor = ToolExecutor(registry, permission)
        result = await executor.execute("calculator", "2+2", user="guest")
        assert not result.success


class TestPermissionManager:
    def test_grant_and_check(self):
        pm = PermissionManager()
        pm.grant("test_tool", PermissionRule(allowed_users=["admin"]))
        ok, _ = pm.check("test_tool", user="admin")
        assert ok
        ok, _ = pm.check("test_tool", user="guest")
        assert not ok

    def test_role_check(self):
        pm = PermissionManager()
        pm.grant("tool_a", PermissionRule(allowed_roles=["editor"]))
        ok, _ = pm.check("tool_a", role="editor")
        assert ok
        ok, _ = pm.check("tool_a", role="viewer")
        assert not ok

    def test_call_limit(self):
        pm = PermissionManager()
        pm.grant("limited", PermissionRule(max_calls=2))
        ok, _ = pm.check("limited")
        assert ok
        pm.record_call("limited")
        pm.record_call("limited")
        ok, _ = pm.check("limited")
        assert not ok


class TestCalculatorTool:
    @pytest.mark.asyncio
    async def test_addition(self):
        tool = CalculatorTool()
        call = ToolCallModel(tool_name="calculator", input="3 + 4")
        result = await tool.execute(call)
        assert result.success
        assert result.output == "7"

    @pytest.mark.asyncio
    async def test_invalid_expression(self):
        tool = CalculatorTool()
        call = ToolCallModel(tool_name="calculator", input="invalid @@")
        result = await tool.execute(call)
        assert not result.success


class TestSearchTool:
    @pytest.mark.asyncio
    async def test_search(self):
        tool = SearchTool()
        call = ToolCallModel(tool_name="search", input="test query")
        result = await tool.execute(call)
        assert result.success
        assert "test query" in result.output


class TestFilesystemTool:
    @pytest.mark.asyncio
    async def test_write_and_read(self, tmp_path):
        tool = FilesystemTool()
        test_file = str(tmp_path / "test.txt")
        call = ToolCallModel(tool_name="filesystem", input=f"write {test_file} hello world")
        result = await tool.execute(call)
        assert result.success
        call2 = ToolCallModel(tool_name="filesystem", input=f"read {test_file}")
        result2 = await tool.execute(call2)
        assert result2.success
        assert "hello world" in result2.output

    @pytest.mark.asyncio
    async def test_ls(self, tmp_path):
        tool = FilesystemTool()
        call = ToolCallModel(tool_name="filesystem", input=f"ls {tmp_path}")
        result = await tool.execute(call)
        assert result.success

    @pytest.mark.asyncio
    async def test_unknown_op(self):
        tool = FilesystemTool()
        call = ToolCallModel(tool_name="filesystem", input="invalid_op /tmp")
        result = await tool.execute(call)
        assert not result.success
