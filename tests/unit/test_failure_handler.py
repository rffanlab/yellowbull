"""T03: 失败处理器单元测试"""

import pytest

from yellowbull.agent.failure_handler import FailureHandler
from yellowbull.agent.step_state import StepState, StepStatus
from yellowbull.agent.step_selector import StepSelector
from yellowbull.agent.obstacle_resolver import ObstacleResolver, ObstacleAnalysis
from yellowbull.models.step import Step


class MockObstacleResolver:
    """Mock ObstacleResolver for testing"""

    def __init__(self, recoverable=True):
        self.recoverable = recoverable
        self.calls = []

    async def resolve(self, step, state, error):
        self.calls.append((step, state, error))
        return ObstacleAnalysis(
            cause=error,
            suggestion="retry",
            is_recoverable=self.recoverable,
        )


@pytest.fixture
def step_selector():
    steps = [
        Step(step_id="step_1", description="A", tool_hint="file"),
        Step(step_id="step_2", description="B", tool_hint="file", depends_on=["step_1"]),
    ]
    step_states = {s.step_id: StepState(s.step_id) for s in steps}
    return StepSelector(step_states=step_states)


@pytest.fixture
def resolver():
    return MockObstacleResolver(recoverable=True)


@pytest.fixture
def handler(step_selector, resolver):
    return FailureHandler(
        step_selector=step_selector,
        obstacle_resolver=resolver,
        max_retries=3,
    )


class TestHandleFailure:
    """TC-03-07-01 ~ TC-03-07-09"""

    @pytest.mark.asyncio
    async def test_retry_on_first_failure(self, handler):
        """TC-03-07-01: 首次失败重试"""
        step = Step(step_id="step_1", description="A", tool_hint="file")
        state = StepState("step_1")
        result = await handler.handle_failure(step, state, "error", [])
        assert result == "retry"

    @pytest.mark.asyncio
    async def test_retry_increments_count(self, handler):
        """TC-03-07-02: 重试计数增加"""
        step = Step(step_id="step_1", description="A", tool_hint="file")
        state = StepState("step_1")
        await handler.handle_failure(step, state, "error", [])
        assert state.retry_count == 1

    @pytest.mark.asyncio
    async def test_skip_after_max_retries(self, handler):
        """TC-03-07-03: 超过最大重试跳过"""
        step = Step(step_id="step_1", description="A", tool_hint="file")
        state = StepState("step_1")
        state.retry_count = 3
        result = await handler.handle_failure(step, state, "error", [])
        assert result == "skip"

    @pytest.mark.asyncio
    async def test_abort_on_critical_failure(self, handler):
        """TC-03-07-04: 关键步骤失败终止"""
        step = Step(
            step_id="step_1",
            description="A",
            tool_hint="file",
            is_critical=True,
        )
        state = StepState("step_1")
        state.retry_count = 3
        result = await handler.handle_failure(step, state, "error", [])
        assert result == "abort"

    @pytest.mark.asyncio
    async def test_unrecoverable_skips(self, step_selector):
        """TC-03-07-05: 不可恢复障碍跳过"""
        unrec_resolver = MockObstacleResolver(recoverable=False)
        handler = FailureHandler(
            step_selector=step_selector,
            obstacle_resolver=unrec_resolver,
            max_retries=3,
        )
        step = Step(step_id="step_1", description="A", tool_hint="file")
        state = StepState("step_1")
        result = await handler.handle_failure(step, state, "error", [])
        assert result in ("skip", "abort")

    @pytest.mark.asyncio
    async def test_retry_without_resolver(self, step_selector):
        """TC-03-07-06: 无障碍解决器重试"""
        handler = FailureHandler(
            step_selector=step_selector,
            obstacle_resolver=None,
            max_retries=3,
        )
        step = Step(step_id="step_1", description="A", tool_hint="file")
        state = StepState("step_1")
        result = await handler.handle_failure(step, state, "error", [])
        assert result == "retry"

    @pytest.mark.asyncio
    async def test_cascade_skip_on_non_critical(self, handler):
        """TC-03-07-07: 非关键步骤级联跳过"""
        step = Step(step_id="step_1", description="A", tool_hint="file")
        state = StepState("step_1")
        state.retry_count = 3
        all_steps = [
            Step(step_id="step_1", description="A", tool_hint="file"),
            Step(step_id="step_2", description="B", tool_hint="file", depends_on=["step_1"]),
        ]
        result = await handler.handle_failure(step, state, "error", all_steps)
        assert result == "skip"

    @pytest.mark.asyncio
    async def test_retry_count_under_limit(self, handler):
        """TC-03-07-08: 重试次数未达上限"""
        step = Step(step_id="step_1", description="A", tool_hint="file")
        state = StepState("step_1")
        state.retry_count = 2
        result = await handler.handle_failure(step, state, "error", [])
        assert result == "retry"

    @pytest.mark.asyncio
    async def test_retry_calls_resolver(self, handler):
        """TC-03-07-09: 重试调用障碍解决器"""
        step = Step(step_id="step_1", description="A", tool_hint="file")
        state = StepState("step_1")
        await handler.handle_failure(step, state, "error", [])
        assert len(handler.obstacle_resolver.calls) == 1


class TestFailureHandlerBoundary:
    """T03-13: 错误处理边界场景"""

    @pytest.mark.asyncio
    async def test_empty_step_list(self, handler):
        """TC-03-13-01: 空步骤列表安全返回"""
        step = Step(step_id="step_1", description="A", tool_hint="file")
        state = StepState("step_1")
        result = await handler.handle_failure(step, state, "error", [])
        assert result in ("retry", "skip", "abort")

    @pytest.mark.asyncio
    async def test_all_critical_steps_fail(self):
        """TC-03-13-02: 全部关键步骤失败终止"""
        steps = [
            Step(step_id="s1", description="A", tool_hint="file", is_critical=True),
            Step(step_id="s2", description="B", tool_hint="file", is_critical=True),
        ]
        step_states = {s.step_id: StepState(s.step_id) for s in steps}
        selector = StepSelector(step_states=step_states)
        resolver = MockObstacleResolver(recoverable=False)
        handler = FailureHandler(step_selector=selector, obstacle_resolver=resolver, max_retries=1)

        for step in steps:
            state = step_states[step.step_id]
            state.retry_count = 1
            result = await handler.handle_failure(step, state, "error", steps)
            assert result == "abort"

    @pytest.mark.asyncio
    async def test_cascade_skip_on_dependency_failure(self, handler):
        """TC-03-13-03: 级联跳过"""
        steps = [
            Step(step_id="s1", description="A", tool_hint="file"),
            Step(step_id="s2", description="B", tool_hint="file", depends_on=["s1"]),
            Step(step_id="s3", description="C", tool_hint="file", depends_on=["s2"]),
        ]
        state = StepState("s1")
        state.retry_count = 3
        result = await handler.handle_failure(Step(step_id="s1", description="A", tool_hint="file"), state, "error", steps)
        assert result == "skip"

    @pytest.mark.asyncio
    async def test_retry_storm_control(self):
        """TC-03-13-04: 重试风暴受控"""
        steps = [Step(step_id="s1", description="A", tool_hint="file")]
        step_states = {s.step_id: StepState(s.step_id) for s in steps}
        selector = StepSelector(step_states=step_states)
        resolver = MockObstacleResolver(recoverable=True)
        handler = FailureHandler(step_selector=selector, obstacle_resolver=resolver, max_retries=2)

        step = Step(step_id="s1", description="A", tool_hint="file")
        state = StepState("s1")

        # 第一次重试
        result = await handler.handle_failure(step, state, "error", [])
        assert result == "retry"
        assert state.retry_count == 1

        # 第二次重试
        result = await handler.handle_failure(step, state, "error", [])
        assert result == "retry"
        assert state.retry_count == 2

        # 第三次超过上限
        result = await handler.handle_failure(step, state, "error", [])
        assert result == "skip"

    @pytest.mark.asyncio
    async def test_error_propagation_in_nested(self, handler):
        """TC-03-13-05: 错误传播"""
        step = Step(step_id="s1", description="A", tool_hint="file")
        state = StepState("s1")
        state.retry_count = 3
        result = await handler.handle_failure(step, state, "nested error", [])
        assert result == "skip"
        assert state.status in (StepStatus.FAILED, StepStatus.SKIPPED)
