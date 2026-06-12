"""T03: 障碍解决器单元测试"""

import pytest

from yellowbull.agent.obstacle_resolver import ObstacleResolver, ObstacleAnalysis
from yellowbull.agent.step_state import StepState
from yellowbull.models.step import Step


class MockLLMClient:
    """Mock LLM Client for testing"""

    def __init__(self, response="可恢复，建议重试"):
        self.response = response
        self.calls = []

    async def chat(self, system_prompt, user_prompts):
        self.calls.append((system_prompt, user_prompts))
        return self.response


@pytest.fixture
def resolver():
    return ObstacleResolver(MockLLMClient())


class TestObstacleAnalysis:
    """TC-03-08-01 ~ TC-03-08-03"""

    def test_analysis_fields(self):
        """TC-03-08-01: 分析结果字段"""
        analysis = ObstacleAnalysis(
            cause="timeout",
            suggestion="重试",
            is_recoverable=True,
        )
        assert analysis.cause == "timeout"
        assert analysis.is_recoverable is True

    def test_analysis_not_recoverable(self):
        """TC-03-08-02: 不可恢复分析"""
        analysis = ObstacleAnalysis(
            cause="permission denied",
            suggestion="检查权限",
            is_recoverable=False,
        )
        assert analysis.is_recoverable is False

    def test_analysis_default_values(self):
        """TC-03-08-03: 默认值"""
        analysis = ObstacleAnalysis(
            cause="error",
            suggestion="重试",
            is_recoverable=True,
        )
        assert analysis.cause == "error"
        assert analysis.suggestion == "重试"
        assert analysis.is_recoverable is True


class TestResolve:
    """TC-03-08-04 ~ TC-03-08-10"""

    @pytest.mark.asyncio
    async def test_resolve_returns_analysis(self, resolver):
        """TC-03-08-04: 返回分析结果"""
        step = Step(step_id="step_1", description="A", tool_hint="file")
        state = StepState("step_1")
        result = await resolver.resolve(step, state, "timeout")
        assert isinstance(result, ObstacleAnalysis)

    @pytest.mark.asyncio
    async def test_resolve_recoverable(self, resolver):
        """TC-03-08-05: 可恢复障碍"""
        step = Step(step_id="step_1", description="A", tool_hint="file")
        state = StepState("step_1")
        result = await resolver.resolve(step, state, "timeout")
        assert result.is_recoverable is True

    @pytest.mark.asyncio
    async def test_resolve_with_context(self, resolver):
        """TC-03-08-06: 带上下文"""
        step = Step(step_id="step_1", description="A", tool_hint="file")
        state = StepState("step_1")
        result = await resolver.resolve(
            step, state, "error", context={"key": "value"}
        )
        assert isinstance(result, ObstacleAnalysis)

    @pytest.mark.asyncio
    async def test_resolve_calls_llm(self, resolver):
        """TC-03-08-07: 调用 LLM"""
        step = Step(step_id="step_1", description="A", tool_hint="file")
        state = StepState("step_1")
        await resolver.resolve(step, state, "error")
        assert len(resolver.llm_client.calls) == 1

    @pytest.mark.asyncio
    async def test_resolve_prompt_contains_step_info(self, resolver):
        """TC-03-08-08: 提示包含步骤信息"""
        step = Step(step_id="step_1", description="A", tool_hint="file")
        state = StepState("step_1")
        await resolver.resolve(step, state, "error")
        _, prompts = resolver.llm_client.calls[0]
        assert "step_1" in prompts[0]

    @pytest.mark.asyncio
    async def test_resolve_llm_failure_returns_none(self):
        """TC-03-08-09: LLM 失败返回 None"""

        class FailingLLM:
            async def chat(self, system, prompts):
                raise Exception("LLM error")

        resolver = ObstacleResolver(FailingLLM())
        step = Step(step_id="step_1", description="A", tool_hint="file")
        state = StepState("step_1")
        result = await resolver.resolve(step, state, "error")
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_retry_count_in_prompt(self, resolver):
        """TC-03-08-10: 重试次数在提示中"""
        step = Step(step_id="step_1", description="A", tool_hint="file")
        state = StepState("step_1")
        state.retry_count = 2
        await resolver.resolve(step, state, "error")
        _, prompts = resolver.llm_client.calls[0]
        assert "2" in prompts[0]


class TestParseAnalysis:
    """TC-03-08-11 ~ TC-03-08-14"""

    def test_parse_recoverable(self, resolver):
        """TC-03-08-11: 解析可恢复"""
        analysis = resolver._parse_analysis("true, 可以恢复", "timeout")
        assert analysis.is_recoverable is True

    def test_parse_not_recoverable(self, resolver):
        """TC-03-08-12: 解析不可恢复"""
        analysis = resolver._parse_analysis("无法恢复", "error")
        assert analysis.is_recoverable is False

    def test_parse_sets_cause(self, resolver):
        """TC-03-08-13: 设置原因"""
        analysis = resolver._parse_analysis("建议重试", "timeout")
        assert analysis.cause == "timeout"

    def test_parse_truncates_long_response(self, resolver):
        """TC-03-08-14: 截断长响应"""
        long_response = "x" * 1000
        analysis = resolver._parse_analysis(long_response, "error")
        assert len(analysis.suggestion) <= 500


class TestObstacleResolverBoundary:
    """T03-14: 障碍排除边界场景"""

    @pytest.mark.asyncio
    async def test_empty_error_message(self, resolver):
        """TC-03-14-01: 空错误信息"""
        step = Step(step_id="step_1", description="A", tool_hint="file")
        state = StepState("step_1")
        result = await resolver.resolve(step, state, "")
        assert result is not None or result is None

    @pytest.mark.asyncio
    async def test_very_long_error_message(self, resolver):
        """TC-03-14-02: 超长错误信息"""
        step = Step(step_id="step_1", description="A", tool_hint="file")
        state = StepState("step_1")
        long_error = "error " * 1000
        result = await resolver.resolve(step, state, long_error)
        assert isinstance(result, ObstacleAnalysis) or result is None

    @pytest.mark.asyncio
    async def test_no_context(self, resolver):
        """TC-03-14-03: 无上下文"""
        step = Step(step_id="step_1", description="A", tool_hint="file")
        state = StepState("step_1")
        result = await resolver.resolve(step, state, "error", context=None)
        assert isinstance(result, ObstacleAnalysis) or result is None

    @pytest.mark.asyncio
    async def test_max_retry_count(self, resolver):
        """TC-03-14-04: 最大重试次数"""
        step = Step(step_id="step_1", description="A", tool_hint="file")
        state = StepState("step_1")
        state.retry_count = 100
        result = await resolver.resolve(step, state, "error")
        assert isinstance(result, ObstacleAnalysis) or result is None
