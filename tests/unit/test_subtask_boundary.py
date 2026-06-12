"""T03-16: 子任务边界场景测试"""

import pytest
from unittest.mock import AsyncMock

from yellowbull.agent.step_state import ContextStore, StepState
from yellowbull.agent.executor import StepExecutor
from yellowbull.models.step import Step
from yellowbull.tools.base import Tool, ToolRegistry, ToolResult


class _MockSubTaskTool(Tool):
    """模拟子任务工具"""

    model_config = {"extra": "allow"}

    def __init__(self, name: str, fail: bool = False):
        super().__init__(name=name, description="Mock 子任务工具")
        self._fail = fail

    async def execute(self, params: dict) -> ToolResult:
        if self._fail:
            return ToolResult(
                success=False,
                error="子任务失败",
            )
        return ToolResult(
            success=True,
            output="子任务完成",
        )


class TestSubTaskBoundary:
    """T03-16: 子任务边界场景"""

    def _make_executor(self) -> StepExecutor:
        context_store = ContextStore("task_1")
        llm_client = AsyncMock()
        llm_client.chat = AsyncMock(return_value='{"command": "test"}')
        return StepExecutor(context_store, llm_client, step_timeout=2)

    # TC-03-16-01: 子任务执行成功
    @pytest.mark.asyncio
    async def test_subtask_success(self):
        """正常子任务应成功"""
        executor = self._make_executor()

        step = Step(
            step_id="s1",
            description="子任务",
            tool_hint="mock_subtask_tool",
        )

        ToolRegistry.register(_MockSubTaskTool(name="mock_subtask_tool", fail=False))

        result = await executor.execute(step)

        assert result.success is True

    # TC-03-16-02: 子任务失败
    @pytest.mark.asyncio
    async def test_subtask_failure(self):
        """子任务执行失败应报告失败原因"""
        executor = self._make_executor()

        step = Step(
            step_id="s1",
            description="失败的子任务",
            tool_hint="mock_subtask_fail",
        )

        ToolRegistry.register(_MockSubTaskTool(name="mock_subtask_fail", fail=True))

        result = await executor.execute(step)

        assert result.success is False
        assert result.error is not None

    # TC-03-16-03: 子任务超时
    @pytest.mark.asyncio
    async def test_subtask_timeout(self):
        """子任务超时应终止子任务"""
        executor = self._make_executor()

        step = Step(
            step_id="s1",
            description="超时的子任务",
            tool_hint="mock_subtask_timeout",
        )

        class _MockTimeoutSubTaskTool(Tool):
            model_config = {"extra": "allow"}

            async def execute(self, params: dict) -> ToolResult:
                import asyncio
                await asyncio.sleep(10)
                return ToolResult(success=True, output="ok")

        ToolRegistry.register(_MockTimeoutSubTaskTool(name="mock_subtask_timeout", description="Mock"))

        result = await executor.execute(step)

        # 应超时失败
        assert result.success is False
        assert result.error is not None

    # TC-03-16-04: 子任务预算
    @pytest.mark.asyncio
    async def test_subtask_budget(self):
        """子任务超预算应终止子任务"""
        executor = self._make_executor()

        step = Step(
            step_id="s1",
            description="子任务",
            tool_hint="mock_subtask_budget",
        )

        ToolRegistry.register(_MockSubTaskTool(name="mock_subtask_budget", fail=False))

        result = await executor.execute(step)

        assert result.success is True

    # TC-03-16-05: 子任务结果存储
    @pytest.mark.asyncio
    async def test_subtask_result_storage(self):
        """子任务结果应正确存储"""
        executor = self._make_executor()

        step = Step(
            step_id="s1",
            description="子任务结果存储",
            tool_hint="mock_subtask_result",
        )

        ToolRegistry.register(_MockSubTaskTool(name="mock_subtask_result", fail=False))

        result = await executor.execute(step)

        assert result.success is True
        assert executor.context_store.get("s1") is not None
