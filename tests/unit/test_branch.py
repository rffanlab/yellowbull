"""T03-02: 分支处理测试"""

import pytest
from unittest.mock import AsyncMock, patch

from yellowbull.agent.step_state import ContextStore, StepState
from yellowbull.agent.executor import StepExecutor, BranchResult
from yellowbull.models.step import Step


@pytest.fixture
def context_store():
    return ContextStore("task_1")


@pytest.fixture
def llm_client():
    client = AsyncMock()
    client.chat = AsyncMock(return_value="true")
    return client


@pytest.fixture
def executor(context_store, llm_client):
    return StepExecutor(context_store, llm_client, step_timeout=2)


class TestBranchHandling:
    """TC-03-02-01 ~ TC-03-02-03"""

    @pytest.mark.asyncio
    async def test_branch_condition_evaluation(self, executor):
        """TC-03-02-01: 条件分支应正确评估并选择路径"""
        branch_step = Step(
            step_id="b1",
            description="检查文件是否存在",
            tool_hint="file",
            true_next=["t1"],
            false_next=["f1"],
            branch_condition="文件存在",
        )

        with patch.object(executor, "execute", new_callable=AsyncMock) as mock_execute:
            from yellowbull.agent.executor import StepResultData

            mock_execute.return_value = StepResultData(
                step_id="b1", success=True, result={"exists": True}
            )

            result = await executor.execute_branch(branch_step)

            assert isinstance(result, BranchResult)
            assert result.condition_met is not None

    @pytest.mark.asyncio
    async def test_true_branch_activated(self, executor):
        """TC-03-02-02: 条件为真时应激活 true_next"""
        branch_step = Step(
            step_id="b1",
            description="检查服务状态",
            tool_hint="shell",
            true_next=["t1", "t2"],
            false_next=["f1"],
            branch_condition="服务运行中",
        )

        with patch.object(executor, "execute", new_callable=AsyncMock) as mock_execute:
            from yellowbull.agent.executor import StepResultData

            mock_execute.return_value = StepResultData(
                step_id="b1", success=True, result={"status": "running"}
            )

            executor.llm_client.chat = AsyncMock(return_value="true")

            result = await executor.execute_branch(branch_step)

            assert result.condition_met is True
            assert set(result.activated_steps) == {"t1", "t2"}
            assert set(result.skipped_steps) == {"f1"}

    @pytest.mark.asyncio
    async def test_false_branch_activated(self, executor):
        """TC-03-02-03: 条件为假时应激活 false_next"""
        branch_step = Step(
            step_id="b1",
            description="检查配置",
            tool_hint="file",
            true_next=["t1"],
            false_next=["f1", "f2"],
            branch_condition="配置文件存在",
        )

        with patch.object(executor, "execute", new_callable=AsyncMock) as mock_execute:
            from yellowbull.agent.executor import StepResultData

            mock_execute.return_value = StepResultData(
                step_id="b1", success=True, result={"exists": False}
            )

            executor.llm_client.chat = AsyncMock(return_value="false")

            result = await executor.execute_branch(branch_step)

            assert result.condition_met is False
            assert set(result.activated_steps) == {"f1", "f2"}
            assert set(result.skipped_steps) == {"t1"}


class TestBranchFailure:
    """TC-03-02 失败场景"""

    @pytest.mark.asyncio
    async def test_branch_step_failure(self, executor):
        """分支步骤执行失败时所有分支跳过"""
        branch_step = Step(
            step_id="b1",
            description="检查状态",
            tool_hint="shell",
            true_next=["t1"],
            false_next=["f1"],
            branch_condition="条件",
        )

        with patch.object(executor, "execute", new_callable=AsyncMock) as mock_execute:
            from yellowbull.agent.executor import StepResultData

            mock_execute.return_value = StepResultData(
                step_id="b1", success=False, error="执行失败"
            )

            result = await executor.execute_branch(branch_step)

            assert result.condition_met is False
            assert result.activated_steps == []
            assert set(result.skipped_steps) == {"t1", "f1"}


class TestBranchConditionEvaluation:
    """TC-03-02 条件评估"""

    @pytest.mark.asyncio
    async def test_condition_true_response(self, executor):
        """LLM 返回 true 时条件满足"""
        result = await executor._evaluate_branch_condition(
            "文件存在", {"exists": True}
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_condition_false_response(self, executor):
        """LLM 返回 false 时条件不满足"""
        executor.llm_client.chat = AsyncMock(return_value="false")

        result = await executor._evaluate_branch_condition(
            "文件存在", {"exists": False}
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_condition_evaluation_error(self, executor):
        """LLM 评估失败时默认 false"""
        executor.llm_client.chat = AsyncMock(side_effect=Exception("网络错误"))

        result = await executor._evaluate_branch_condition(
            "文件存在", {"exists": True}
        )
        assert result is False


class TestBranchEmpty:
    """TC-03-02 空分支"""

    @pytest.mark.asyncio
    async def test_empty_true_next(self, executor):
        """true_next 为空时正确处理"""
        branch_step = Step(
            step_id="b1",
            description="检查",
            tool_hint="file",
            true_next=[],
            false_next=["f1"],
            branch_condition="条件",
        )

        with patch.object(executor, "execute", new_callable=AsyncMock) as mock_execute:
            from yellowbull.agent.executor import StepResultData

            mock_execute.return_value = StepResultData(
                step_id="b1", success=True, result={}
            )

            executor.llm_client.chat = AsyncMock(return_value="true")

            result = await executor.execute_branch(branch_step)

            assert result.condition_met is True
            assert result.activated_steps == []
            assert set(result.skipped_steps) == {"f1"}

    @pytest.mark.asyncio
    async def test_empty_false_next(self, executor):
        """false_next 为空时正确处理"""
        branch_step = Step(
            step_id="b1",
            description="检查",
            tool_hint="file",
            true_next=["t1"],
            false_next=[],
            branch_condition="条件",
        )

        with patch.object(executor, "execute", new_callable=AsyncMock) as mock_execute:
            from yellowbull.agent.executor import StepResultData

            mock_execute.return_value = StepResultData(
                step_id="b1", success=True, result={}
            )

            executor.llm_client.chat = AsyncMock(return_value="false")

            result = await executor.execute_branch(branch_step)

            assert result.condition_met is False
            assert result.activated_steps == []  # false_next 为空
            assert set(result.skipped_steps) == {"t1"}  # true_next 被跳过
