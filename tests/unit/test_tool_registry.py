"""T00-06: 工具系统基类单元测试"""

import pytest

from yellowbull.tools.base import SideEffectType, Tool, ToolRegistry, ToolResult


class _TestTool(Tool):
    """测试用工具"""

    def __init__(self, name: str = "test_tool"):
        super().__init__(
            name=name,
            description="A test tool",
            side_effects=[],
            is_safe=True,
        )

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, output="done")


@pytest.fixture(autouse=True)
def clear_registry():
    """每次测试前清空注册表"""
    ToolRegistry._tools = {}
    yield
    ToolRegistry._tools = {}


class TestToolBase:
    """Tool 基类"""

    def test_tool_creation(self):
        tool = _TestTool()
        assert tool.name == "test_tool"
        assert tool.is_safe is True

    def test_tool_with_side_effects(self):
        """TC-00-06-05: 副作用声明"""
        tool = _TestTool()
        tool.side_effects = [SideEffectType.FILE_WRITE]
        assert SideEffectType.FILE_WRITE in tool.side_effects

    def test_tool_execute_not_implemented(self):
        """未实现 execute 应抛出 NotImplementedError"""

        class EmptyTool(Tool):
            def __init__(self):
                super().__init__(name="empty", description="empty")

        tool = EmptyTool()
        with pytest.raises(NotImplementedError):
            import asyncio
            asyncio.get_event_loop().run_until_complete(tool.execute({}))

    def test_tool_validate_params_default(self):
        tool = _TestTool()
        assert tool.validate_params({}) is True


class TestToolResult:
    """ToolResult 模型"""

    def test_success_result(self):
        result = ToolResult(success=True, output="data")
        assert result.success is True
        assert result.output == "data"
        assert result.error is None

    def test_error_result(self):
        result = ToolResult(success=False, error="something failed")
        assert result.success is False
        assert result.error == "something failed"

    def test_result_with_side_effects(self):
        result = ToolResult(success=True, output="ok", side_effects=["file_write:/tmp/x"])
        assert len(result.side_effects) == 1


class TestToolRegistry:
    """TC-00-06-01 ~ TC-00-06-05: 工具注册表"""

    def test_register_tool(self):
        """TC-00-06-01: 工具注册"""
        tool = _TestTool()
        ToolRegistry.register(tool)
        assert ToolRegistry.get("test_tool") is not None

    def test_get_tool(self):
        """TC-00-06-02: 工具获取"""
        tool = _TestTool()
        ToolRegistry.register(tool)
        retrieved = ToolRegistry.get("test_tool")
        assert retrieved is tool

    def test_list_all_tools(self):
        """TC-00-06-03: 工具列表"""
        ToolRegistry.register(_TestTool(name="tool_a"))
        ToolRegistry.register(_TestTool(name="tool_b"))
        tools = ToolRegistry.list_all()
        assert len(tools) == 2

    def test_match_by_hint(self):
        """TC-00-06-03: hint 匹配"""
        ToolRegistry.register(_TestTool(name="file_reader"))
        ToolRegistry.register(_TestTool(name="shell_runner"))
        matches = ToolRegistry.match_by_hint("file")
        assert len(matches) >= 1
        assert any("file" in t.name.lower() for t in matches)

    def test_get_nonexistent_tool(self):
        """TC-00-06-04: 未知工具"""
        result = ToolRegistry.get("nonexistent")
        assert result is None

    def test_match_by_hint_no_match(self):
        ToolRegistry.register(_TestTool(name="tool_a"))
        matches = ToolRegistry.match_by_hint("nonexistent_hint")
        assert matches == []

    def test_register_overwrite(self):
        tool1 = _TestTool(name="same_name")
        tool2 = _TestTool(name="same_name")
        ToolRegistry.register(tool1)
        ToolRegistry.register(tool2)
        assert ToolRegistry.get("same_name") is tool2
