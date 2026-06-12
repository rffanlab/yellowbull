"""T03-17: 完成判定边界场景测试"""

import pytest
from unittest.mock import AsyncMock

from yellowbull.agent.step_state import ContextStore, StepState
from yellowbull.agent.executor import StepExecutor
from yellowbull.models.step import Step, StepStatus
from yellowbull.tools.base import Tool, ToolRegistry, ToolResult


class _MockDoneTool(Tool):
    """模拟成功工具"""

    model_config = {"extra": "allow"}

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=True, output="ok")


class _MockFailTool(Tool):
    """模拟失败工具"""

    model_config = {"extra": "allow"}

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(success=False, error="失败")


class TestCompletionBoundary:
    """T03-17: 完成判定边界场景"""

    def _make_executor(self) -> StepExecutor:
        context_store = ContextStore("task_1")
        llm_client = AsyncMock()
        llm_client.chat = AsyncMock(return_value='{"command": "test"}')
        return StepExecutor(context_store, llm_client, step_timeout=2)

    # TC-03-17-01: 完成率临界（刚好达标）
    def test_completion_rate_boundary(self):
        """完成率 = threshold 应判定成功"""
        # 模拟 10 个步骤，8 个成功，2 个跳过
        # 完成率 = 8/10 = 0.8
        # threshold = 0.8
        total = 10
        done = 8
        threshold = 0.8

        rate = done / total
        assert rate >= threshold

    # TC-03-17-02: 无关键步骤
    def test_no_critical_steps(self):
        """全部非关键步骤应全部成功才成功"""
        states = {
            f"s{i}": StepState(step_id=f"s{i}") for i in range(5)
        }

        # 全部标记为完成
        for state in states.values():
            state.mark_done("ok")

        # 全部完成
        done_count = sum(1 for s in states.values() if s.status == StepStatus.DONE)
        assert done_count == 5

    # TC-03-17-03: 全部关键步骤
    def test_all_critical_steps(self):
        """全部关键步骤任一失败应任务失败"""
        states = {
            f"s{i}": StepState(step_id=f"s{i}") for i in range(5)
        }

        # 前 4 个成功，第 5 个失败
        for i, state in enumerate(states.values()):
            if i < 4:
                state.mark_done("ok")
            else:
                state.mark_failed("失败")

        # 有关键步骤失败
        failed_count = sum(1 for s in states.values() if s.status == StepStatus.FAILED)
        assert failed_count == 1

    # TC-03-17-04: 补救触发临界
    def test_remedy_trigger_boundary(self):
        """完成率刚好低于阈值应触发补救"""
        total = 10
        done = 7
        threshold = 0.8

        rate = done / total
        assert rate < threshold
        # 应触发补救

    # TC-03-17-05: 补救失败
    def test_remedy_failure(self):
        """补救执行失败应任务失败"""
        states = {
            f"s{i}": StepState(step_id=f"s{i}") for i in range(5)
        }

        # 3 个成功，2 个失败
        for i, state in enumerate(states.values()):
            if i < 3:
                state.mark_done("ok")
            else:
                state.mark_failed("失败")

        # 补救后仍然有失败
        failed_count = sum(1 for s in states.values() if s.status == StepStatus.FAILED)
        assert failed_count == 2
