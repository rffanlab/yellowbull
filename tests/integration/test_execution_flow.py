"""T03-17: 完整执行流程集成测试"""

import asyncio
import pytest
from unittest.mock import AsyncMock

from yellowbull.agent.step_state import ContextStore, StepState
from yellowbull.agent.executor import StepExecutor
from yellowbull.agent.guard import BudgetGuard
from yellowbull.models.step import Step
from yellowbull.tools.base import Tool, ToolRegistry, ToolResult


class _MockSuccessTool(Tool):
    """模拟成功工具"""

    model_config = {"extra": "allow"}

    def __init__(self, name: str, fail: bool = False):
        super().__init__(name=name, description="Mock 成功工具")
        self._fail = fail

    async def execute(self, params: dict) -> ToolResult:
        if self._fail:
            return ToolResult(
                success=False,
                error="执行失败",
            )
        return ToolResult(
            success=True,
            output="执行成功",
        )


class TestExecutionFlow:
    """T03-17: 完整执行流程集成测试"""

    def _make_executor(self) -> StepExecutor:
        context_store = ContextStore("task_1")
        llm_client = AsyncMock()
        llm_client.chat = AsyncMock(return_value='{"command": "test"}')
        return StepExecutor(context_store, llm_client, step_timeout=2)

    # TC-03-17-01: 完整执行流程
    @pytest.mark.asyncio
    async def test_full_execution_flow(self):
        """正常流程: 接收→拆解→执行→完成"""
        executor = self._make_executor()

        ToolRegistry.register(_MockSuccessTool(name="mock_success_tool"))

        step = Step(
            step_id="s1",
            description="完整流程",
            tool_hint="mock_success_tool",
        )

        result = await executor.execute(step)

        assert result.success is True
        assert executor.context_store.get("s1") is not None

    # TC-03-17-02: 错误处理流程
    @pytest.mark.asyncio
    async def test_error_handling_flow(self):
        """错误流程: 失败→分析→修正"""
        executor = self._make_executor()

        ToolRegistry.register(_MockSuccessTool(name="mock_error_tool", fail=True))

        step = Step(
            step_id="s1",
            description="错误流程",
            tool_hint="mock_error_tool",
        )

        result = await executor.execute(step)

        assert result.success is False
        assert result.error is not None

    # TC-03-17-03: 错误流程（永久失败）
    @pytest.mark.asyncio
    async def test_error_flow_permanent_failure(self):
        """永久失败应正确终止"""
        executor = self._make_executor()

        ToolRegistry.register(_MockSuccessTool(name="mock_permanent_fail", fail=True))

        step = Step(
            step_id="s1",
            description="永久失败",
            tool_hint="mock_permanent_fail",
        )

        result = await executor.execute(step)

        assert result.success is False

    # TC-03-17-04: 预算保护流程
    @pytest.mark.asyncio
    async def test_budget_protection_flow(self):
        """预算保护应正确触发"""
        guard = BudgetGuard(max_total_steps=2)
        guard.start()
        guard.consume_step()
        guard.consume_step()

        result = guard.check()
        assert result.ok is False

    # TC-03-17-05: 超时保护流程
    @pytest.mark.asyncio
    async def test_timeout_protection_flow(self):
        """超时保护应正确触发"""
        guard = BudgetGuard(max_total_steps=100, total_timeout=0)
        guard.start()

        import time
        await asyncio.sleep(0.01)

        result = guard.check()
        assert result.ok is False
