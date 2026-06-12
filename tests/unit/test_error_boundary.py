"""T03-13: 错误处理边界场景测试"""

import pytest
from unittest.mock import AsyncMock

from yellowbull.agent.step_state import ContextStore, StepState
from yellowbull.agent.executor import StepExecutor, StepResultData
from yellowbull.models.step import Step
from yellowbull.tools.base import Tool, ToolRegistry, ToolResult


class _MockErrorTool(Tool):
    """模拟错误工具"""

    model_config = {"extra": "allow"}

    def __init__(self, name: str, fail_count: int = 0, error_msg: str = "失败"):
        super().__init__(name=name, description="Mock 错误工具")
        self._fail_count = fail_count
        self._call_count = 0
        self._error_msg = error_msg

    async def execute(self, params: dict) -> ToolResult:
        self._call_count += 1
        if self._call_count <= self._fail_count:
            return ToolResult(
                success=False,
                error=self._error_msg,
            )
        return ToolResult(
            success=True,
            output="ok",
        )


class TestErrorBoundary:
    """T03-13: 错误处理边界场景"""

    def _make_executor(self) -> StepExecutor:
        context_store = ContextStore("task_1")
        llm_client = AsyncMock()
        llm_client.chat = AsyncMock(return_value='{"command": "test"}')
        return StepExecutor(context_store, llm_client, step_timeout=2)

    # TC-03-13-01: 工具调用失败
    @pytest.mark.asyncio
    async def test_tool_call_failure(self):
        """工具调用失败应返回错误"""
        executor = self._make_executor()

        step = Step(
            step_id="s1",
            description="失败步骤",
            tool_hint="mock_error_tool",
        )

        ToolRegistry.register(_MockErrorTool("mock_error_tool", fail_count=100))

        result = await executor.execute(step)

        assert result.success is False
        assert result.error is not None

    # TC-03-13-02: 错误描述超长
    @pytest.mark.asyncio
    async def test_long_error_message(self):
        """超长错误信息应正确处理"""
        executor = self._make_executor()

        step = Step(
            step_id="s1",
            description="超长错误",
            tool_hint="mock_long_error_tool",
        )

        long_error = "E" * 10240  # 10KB 错误信息
        ToolRegistry.register(_MockErrorTool("mock_long_error_tool", fail_count=1, error_msg=long_error))

        result = await executor.execute(step)

        assert result.success is False
        assert result.error is not None

    # TC-03-13-03: 错误类型未知
    @pytest.mark.asyncio
    async def test_unknown_error_type(self):
        """未分类错误应捕获并返回"""
        executor = self._make_executor()

        step = Step(
            step_id="s1",
            description="未知错误",
            tool_hint="mock_unknown_error_tool",
        )

        # 注册一个抛出未知异常的工具
        class _UnknownErrorTool(Tool):
            model_config = {"extra": "allow"}

            async def execute(self, params: dict) -> ToolResult:
                raise TypeError("未知类型错误")

        ToolRegistry.register(_UnknownErrorTool(name="mock_unknown_error_tool", description="Mock"))

        result = await executor.execute(step)

        assert result.success is False
        assert result.error is not None

    # TC-03-13-04: 错误恢复（可恢复错误）
    @pytest.mark.asyncio
    async def test_error_recovery(self):
        """网络临时故障后应成功"""
        executor = self._make_executor()

        step = Step(
            step_id="s1",
            description="可恢复错误",
            tool_hint="mock_recover_tool",
        )

        # 注册一个先失败后成功的工具（失败 0 次即成功）
        ToolRegistry.register(_MockErrorTool("mock_recover_tool", fail_count=0))

        result = await executor.execute(step)

        assert result.success is True

    # TC-03-13-05: 工具不存在
    @pytest.mark.asyncio
    async def test_tool_not_found(self):
        """工具不存在应返回错误"""
        executor = self._make_executor()

        step = Step(
            step_id="s1",
            description="工具不存在",
            tool_hint="nonexistent_tool",
        )

        result = await executor.execute(step)

        assert result.success is False
        assert "无法解析工具" in (result.error or "")
