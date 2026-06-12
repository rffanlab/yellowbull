"""T03-15: 预算控制边界场景测试"""

import asyncio
import pytest
from unittest.mock import AsyncMock

from yellowbull.agent.step_state import ContextStore
from yellowbull.agent.executor import StepExecutor
from yellowbull.agent.guard import BudgetGuard
from yellowbull.models.step import Step
from yellowbull.tools.base import Tool, ToolRegistry, ToolResult


class _MockBudgetTool(Tool):
    """模拟预算工具"""

    model_config = {"extra": "allow"}

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, output="ok")


class TestBudgetBoundary:
    """T03-15: 预算控制边界场景"""

    def _make_executor(self) -> StepExecutor:
        context_store = ContextStore("task_1")
        llm_client = AsyncMock()
        llm_client.chat = AsyncMock(return_value='{"command": "test"}')
        return StepExecutor(context_store, llm_client, step_timeout=2)

    # TC-03-15-01: 预算为 0
    def test_zero_budget(self):
        """无预算应拒绝执行"""
        guard = BudgetGuard(max_total_steps=0)
        guard.start()

        result = guard.check()
        assert result.ok is False

    # TC-03-15-02: 预算刚好耗尽
    def test_budget_exact_exhaustion(self):
        """预算刚好用完应正常终止"""
        guard = BudgetGuard(max_total_steps=3)
        guard.start()

        # 消耗 3 步
        guard.consume_step()
        guard.consume_step()
        guard.consume_step()

        # 预算耗尽
        result = guard.check()
        assert result.ok is False

    # TC-03-15-03: 预算负值
    def test_negative_budget(self):
        """负预算应拒绝执行"""
        guard = BudgetGuard(max_total_steps=-1)
        guard.start()

        result = guard.check()
        assert result.ok is False

    # TC-03-15-04: 预算消耗过快
    def test_rapid_budget_consumption(self):
        """单步消耗超过总预算应终止"""
        guard = BudgetGuard(max_total_steps=1)
        guard.start()
        guard.consume_step()

        result = guard.check()
        assert result.ok is False

    # TC-03-15-05: 超时临界
    @pytest.mark.asyncio
    async def test_timeout_boundary(self):
        """任务刚好超时应正确终止"""
        guard = BudgetGuard(max_total_steps=100, total_timeout=0)
        guard.start()

        await asyncio.sleep(0.01)  # 短暂等待

        # total_timeout=0 意味着立即超时
        result = guard.check()
        assert result.ok is False

    # TC-03-15-06: 用户取消
    def test_user_cancel(self):
        """取消后应尽快终止"""
        guard = BudgetGuard(max_total_steps=100)
        guard.start()

        # 模拟用户取消
        guard.cancel()

        result = guard.check()
        assert result.ok is False
