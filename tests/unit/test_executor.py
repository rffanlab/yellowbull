"""T03: 步骤执行器单元测试"""

import pytest

from yellowbull.agent.executor import StepExecutor, StepResultData, BranchResult, LoopResult
from yellowbull.agent.step_state import ContextStore, StepState
from yellowbull.models.step import Step


class MockLLMClient:
    """Mock LLM Client for testing"""

    def __init__(self, response="ok"):
        self.response = response
        self.calls = []

    async def chat(self, system_prompt, user_prompts):
        self.calls.append((system_prompt, user_prompts))
        return self.response

    async def generate_tool_calls(self, system_prompt, user_prompts, tools):
        self.calls.append((system_prompt, user_prompts))
        return []


class MockContextStore:
    """Mock ContextStore for testing"""

    def __init__(self, task_id="test_task"):
        self.task_id = task_id
        self._data = {}

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value

    def to_dict(self):
        return self._data.copy()


@pytest.fixture
def context_store():
    return MockContextStore()


@pytest.fixture
def executor(context_store):
    return StepExecutor(
        context_store=context_store,
        llm_client=MockLLMClient(),
        step_timeout=10,
    )


class TestStepResultData:
    """TC-03-06-01 ~ TC-03-06-03"""

    def test_success_result(self):
        """TC-03-06-01: 成功结果"""
        data = StepResultData(
            step_id="step_1",
            success=True,
            result={"key": "value"},
        )
        assert data.success is True
        assert data.result == {"key": "value"}

    def test_failure_result(self):
        """TC-03-06-02: 失败结果"""
        data = StepResultData(
            step_id="step_1",
            success=False,
            error="error",
        )
        assert data.success is False
        assert data.error == "error"

    def test_default_values(self):
        """TC-03-06-03: 默认值"""
        data = StepResultData(step_id="step_1", success=True)
        assert data.result is None
        assert data.error is None
        assert data.tool_used == ""
        assert data.duration_ms == 0


class TestBranchResult:
    """TC-03-06-04 ~ TC-03-06-06"""

    def test_condition_met(self):
        """TC-03-06-04: 条件满足"""
        result = BranchResult(
            condition_met=True,
            activated_steps=["step_1"],
            skipped_steps=["step_2"],
        )
        assert result.condition_met is True

    def test_condition_not_met(self):
        """TC-03-06-05: 条件不满足"""
        result = BranchResult(
            condition_met=False,
            activated_steps=["step_2"],
            skipped_steps=["step_1"],
        )
        assert result.condition_met is False

    def test_default_values(self):
        """TC-03-06-06: 默认值"""
        result = BranchResult(condition_met=False)
        assert result.activated_steps == []
        assert result.skipped_steps == []


class TestLoopResult:
    """TC-03-06-07 ~ TC-03-06-09"""

    def test_loop_results(self):
        """TC-03-06-07: 循环结果"""
        result = LoopResult(
            iterations=2,
            success_count=2,
            failed_count=0,
        )
        assert result.iterations == 2
        assert result.failed_count == 0

    def test_loop_with_failures(self):
        """TC-03-06-08: 循环失败计数"""
        result = LoopResult(
            iterations=2,
            success_count=1,
            failed_count=1,
        )
        assert result.failed_count == 1

    def test_default_values(self):
        """TC-03-06-09: 默认值"""
        result = LoopResult(iterations=0)
        assert result.success_count == 0
        assert result.failed_count == 0
        assert result.results == []


class TestExecutorInit:
    """TC-03-06-10 ~ TC-03-06-12"""

    def test_executor_init(self, executor):
        """TC-03-06-10: 执行器初始化"""
        assert executor.step_timeout == 10

    def test_executor_has_context_store(self, executor):
        """TC-03-06-11: 上下文存储"""
        assert executor.context_store is not None

    def test_executor_has_llm_client(self, executor):
        """TC-03-06-12: LLM 客户端"""
        assert executor.llm_client is not None


class TestToolHintMap:
    """TC-03-06-13 ~ TC-03-06-15"""

    def test_file_hint(self):
        """TC-03-06-13: file 映射"""
        from yellowbull.agent.executor import _TOOL_HINT_MAP
        assert _TOOL_HINT_MAP["file"] == "file_tool"

    def test_shell_hint(self):
        """TC-03-06-14: shell 映射"""
        from yellowbull.agent.executor import _TOOL_HINT_MAP
        assert _TOOL_HINT_MAP["shell"] == "shell_tool"

    def test_code_hint(self):
        """TC-03-06-15: code 映射"""
        from yellowbull.agent.executor import _TOOL_HINT_MAP
        assert _TOOL_HINT_MAP["code"] == "code_tool"
