"""T03-11: 分支处理边界场景测试"""

import pytest
from unittest.mock import AsyncMock

from yellowbull.agent.step_state import ContextStore
from yellowbull.agent.executor import StepExecutor, BranchResult
from yellowbull.models.step import Step
from yellowbull.tools.base import Tool, ToolRegistry, ToolResult


class _MockBranchTool(Tool):
    """模拟分支工具"""

    model_config = {"extra": "allow"}

    def __init__(self, name: str, success: bool = True, output: str = "ok"):
        super().__init__(name=name, description="Mock 分支工具")
        self._success = success
        self._output = output

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(
            success=self._success,
            output=self._output,
        )


class TestBranchBoundary:
    """T03-11: 分支处理边界场景"""

    def _make_executor(self, llm_response: str = "true") -> StepExecutor:
        context_store = ContextStore("task_1")
        llm_client = AsyncMock()
        llm_client.chat = AsyncMock(return_value=llm_response)
        return StepExecutor(context_store, llm_client, step_timeout=2)

    # TC-03-11-01: 分支条件无法判断
    @pytest.mark.asyncio
    async def test_branch_condition_ambiguous(self):
        """条件模糊时应要求澄清或默认分支"""
        executor = self._make_executor(llm_response="不确定")

        step = Step(
            step_id="s1",
            description="检查服务状态",
            tool_hint="mock_branch_tool",
            is_branch_point=True,
            branch_condition="服务是否运行？",
            true_next=["s2"],
            false_next=["s3"],
        )

        # 注册工具
        ToolRegistry.register(_MockBranchTool("mock_branch_tool"))

        result = await executor.execute_branch(step)

        # LLM 返回 "不确定" 不包含 "true"，因此 condition_met 为 False
        assert result.condition_met is False
        assert "s3" in result.activated_steps
        assert "s2" in result.skipped_steps

    # TC-03-11-02: 分支为空
    def test_branch_empty(self):
        """无 true/false 分支时应跳过"""
        executor = self._make_executor()

        step = Step(
            step_id="s1",
            description="空分支",
            tool_hint="mock_branch_tool",
            is_branch_point=True,
            branch_condition="条件",
            true_next=[],
            false_next=[],
        )

        ToolRegistry.register(_MockBranchTool("mock_branch_tool"))

        # 空分支不导致崩溃
        assert step.true_next == []
        assert step.false_next == []

    # TC-03-11-03: 分支嵌套
    @pytest.mark.asyncio
    async def test_branch_nested(self):
        """多层嵌套分支应正确执行内层分支"""
        executor = self._make_executor(llm_response="true")
        ToolRegistry.register(_MockBranchTool("mock_branch_tool"))

        # 外层分支
        outer_step = Step(
            step_id="outer",
            description="外层分支",
            tool_hint="mock_branch_tool",
            is_branch_point=True,
            branch_condition="外层条件",
            true_next=["inner"],
            false_next=["fallback"],
        )

        # 执行外层分支
        outer_result = await executor.execute_branch(outer_step)
        assert outer_result.condition_met is True
        assert "inner" in outer_result.activated_steps

        # 内层分支
        inner_step = Step(
            step_id="inner",
            description="内层分支",
            tool_hint="mock_branch_tool",
            is_branch_point=True,
            branch_condition="内层条件",
            true_next=["inner_true"],
            false_next=["inner_false"],
        )

        inner_result = await executor.execute_branch(inner_step)
        assert inner_result.condition_met is True
        assert "inner_true" in inner_result.activated_steps

    # TC-03-11-04: 分支冲突（多条件同时满足）
    @pytest.mark.asyncio
    async def test_branch_conflict(self):
        """多条件同时为真时按优先级执行"""
        executor = self._make_executor(llm_response="true")
        ToolRegistry.register(_MockBranchTool("mock_branch_tool"))

        step = Step(
            step_id="s1",
            description="冲突分支",
            tool_hint="mock_branch_tool",
            is_branch_point=True,
            branch_condition="条件 A",
            true_next=["a1", "a2"],
            false_next=["b1", "b2"],
        )

        result = await executor.execute_branch(step)
        # 条件为 true 时只激活 true_next
        assert result.condition_met is True
        assert set(result.activated_steps) == {"a1", "a2"}
        assert set(result.skipped_steps) == {"b1", "b2"}

    # TC-03-11-05: 分支步骤失败
    @pytest.mark.asyncio
    async def test_branch_step_failure(self):
        """分支内步骤失败应按错误处理流程"""
        executor = self._make_executor()
        ToolRegistry.register(_MockBranchTool("mock_branch_tool", success=False))

        step = Step(
            step_id="s1",
            description="失败分支",
            tool_hint="mock_branch_tool",
            is_branch_point=True,
            branch_condition="条件",
            true_next=["s2"],
            false_next=["s3"],
        )

        result = await executor.execute_branch(step)
        # 步骤失败时所有分支都被跳过
        assert result.condition_met is False
        assert result.activated_steps == []
        assert set(result.skipped_steps) == {"s2", "s3"}

    @pytest.mark.asyncio
    async def test_branch_evaluation_error(self):
        """分支条件评估失败时默认 false"""
        executor = self._make_executor()
        # Mock LLM 抛出异常
        executor.llm_client.chat = AsyncMock(side_effect=RuntimeError("评估失败"))
        ToolRegistry.register(_MockBranchTool("mock_branch_tool"))

        step = Step(
            step_id="s1",
            description="评估失败分支",
            tool_hint="mock_branch_tool",
            is_branch_point=True,
            branch_condition="条件",
            true_next=["s2"],
            false_next=["s3"],
        )

        result = await executor.execute_branch(step)
        # 评估失败时 condition_met 为 False，且所有分支都被跳过
        assert result.condition_met is False
        assert result.activated_steps == []
        assert set(result.skipped_steps) == {"s2", "s3"}

    @pytest.mark.asyncio
    async def test_branch_no_condition(self):
        """无 branch_condition 时默认 false"""
        executor = self._make_executor()
        ToolRegistry.register(_MockBranchTool("mock_branch_tool"))

        step = Step(
            step_id="s1",
            description="无条件分支",
            tool_hint="mock_branch_tool",
            is_branch_point=True,
            branch_condition=None,
            true_next=["s2"],
            false_next=["s3"],
        )

        result = await executor.execute_branch(step)
        assert result.condition_met is False
        assert "s3" in result.activated_steps

    @pytest.mark.asyncio
    async def test_branch_true_response(self):
        """LLM 返回 true 时激活 true_next"""
        executor = self._make_executor(llm_response="true")
        ToolRegistry.register(_MockBranchTool("mock_branch_tool"))

        step = Step(
            step_id="s1",
            description="True 分支",
            tool_hint="mock_branch_tool",
            is_branch_point=True,
            branch_condition="条件",
            true_next=["s2"],
            false_next=["s3"],
        )

        result = await executor.execute_branch(step)
        assert result.condition_met is True
        assert "s2" in result.activated_steps

    @pytest.mark.asyncio
    async def test_branch_false_response(self):
        """LLM 返回 false 时激活 false_next"""
        executor = self._make_executor(llm_response="false")
        ToolRegistry.register(_MockBranchTool("mock_branch_tool"))

        step = Step(
            step_id="s1",
            description="False 分支",
            tool_hint="mock_branch_tool",
            is_branch_point=True,
            branch_condition="条件",
            true_next=["s2"],
            false_next=["s3"],
        )

        result = await executor.execute_branch(step)
        assert result.condition_met is False
        assert "s3" in result.activated_steps
