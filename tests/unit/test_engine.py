"""T03: 引擎单元测试"""

import pytest

from yellowbull.agent.engine import TaskEngine, TaskRunResult
from yellowbull.agent.guard import BudgetGuard
from yellowbull.agent.step_state import ContextStore, StepState, StepStatus
from yellowbull.models.step import Step
from yellowbull.models.task import Task


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


@pytest.fixture
def engine():
    return TaskEngine(
        llm_client=MockLLMClient(),
        max_total_steps=100,
        total_timeout=1800,
        step_timeout=120,
        max_retries=3,
    )


class TestTaskRunResult:
    """TC-03-12-01 ~ TC-03-12-03"""

    def test_success_result(self):
        """TC-03-12-01: 成功结果"""
        result = TaskRunResult(
            task_id="task_1",
            success=True,
            message="completed",
            steps_executed=5,
        )
        assert result.success is True
        assert result.steps_executed == 5

    def test_failure_result(self):
        """TC-03-12-02: 失败结果"""
        result = TaskRunResult(
            task_id="task_1",
            success=False,
            message="failed",
            steps_failed=1,
        )
        assert result.success is False
        assert result.steps_failed == 1

    def test_default_values(self):
        """TC-03-12-03: 默认值"""
        result = TaskRunResult(task_id="task_1", success=True)
        assert result.steps_executed == 0
        assert result.steps_failed == 0
        assert result.steps_skipped == 0
        assert result.context == {}


class TestEngineInit:
    """TC-03-12-04 ~ TC-03-12-07"""

    def test_engine_init(self, engine):
        """TC-03-12-04: 引擎初始化"""
        assert engine.max_total_steps == 100

    def test_engine_has_llm_client(self, engine):
        """TC-03-12-05: LLM 客户端"""
        assert engine.llm_client is not None

    def test_engine_timeout_config(self, engine):
        """TC-03-12-06: 超时配置"""
        assert engine.total_timeout == 1800
        assert engine.step_timeout == 120

    def test_engine_retry_config(self, engine):
        """TC-03-12-07: 重试配置"""
        assert engine.max_retries == 3


class TestInitStepStates:
    """TC-03-12-08 ~ TC-03-12-10"""

    def test_init_creates_states(self, engine):
        """TC-03-12-08: 创建状态"""
        steps = [
            Step(step_id="step_1", description="A", tool_hint="file"),
            Step(step_id="step_2", description="B", tool_hint="file"),
        ]
        states = engine._init_step_states(steps)
        assert len(states) == 2

    def test_init_states_are_pending(self, engine):
        """TC-03-12-09: 初始状态为待执行"""
        steps = [
            Step(step_id="step_1", description="A", tool_hint="file"),
        ]
        states = engine._init_step_states(steps)
        assert states["step_1"].status == StepStatus.PENDING

    def test_init_all_steps_covered(self, engine):
        """TC-03-12-10: 所有步骤覆盖"""
        steps = [
            Step(step_id="s1", description="A", tool_hint="file"),
            Step(step_id="s2", description="B", tool_hint="file"),
            Step(step_id="s3", description="C", tool_hint="file"),
        ]
        states = engine._init_step_states(steps)
        assert "s1" in states
        assert "s2" in states
        assert "s3" in states


class TestBuildFailureResult:
    """TC-03-12-11 ~ TC-03-12-14"""

    def test_failure_result_counts(self, engine):
        """TC-03-12-11: 失败结果计数"""
        from yellowbull.agent.step_state import ContextStore

        steps = [
            Step(step_id="step_1", description="A", tool_hint="file"),
            Step(step_id="step_2", description="B", tool_hint="file"),
        ]
        states = {
            "step_1": StepState("step_1"),
            "step_2": StepState("step_2"),
        }
        states["step_1"].mark_done({})
        states["step_2"].mark_failed("error")
        context = ContextStore(task_id="task_1")

        result = engine._build_failure_result(
            Task(id="task_1", name="Test", goal="test", confidence=0.5),
            steps,
            states,
            context,
            "test failure",
        )
        assert result.steps_executed == 1
        assert result.steps_failed == 1

    def test_failure_result_task_id(self, engine):
        """TC-03-12-12: 任务 ID"""
        from yellowbull.agent.step_state import ContextStore

        steps = [
            Step(step_id="step_1", description="A", tool_hint="file"),
        ]
        states = engine._init_step_states(steps)
        context = ContextStore(task_id="task_1")

        result = engine._build_failure_result(
            Task(id="task_1", name="Test", goal="test", confidence=0.5),
            steps,
            states,
            context,
            "reason",
        )
        assert result.task_id == "task_1"

    def test_failure_result_message(self, engine):
        """TC-03-12-13: 失败消息"""
        from yellowbull.agent.step_state import ContextStore

        steps = [
            Step(step_id="step_1", description="A", tool_hint="file"),
        ]
        states = engine._init_step_states(steps)
        context = ContextStore(task_id="task_1")

        result = engine._build_failure_result(
            Task(id="task_1", name="Test", goal="test", confidence=0.5),
            steps,
            states,
            context,
            "custom reason",
        )
        assert result.message == "custom reason"

    def test_failure_result_success_false(self, engine):
        """TC-03-12-14: 成功标志为假"""
        from yellowbull.agent.step_state import ContextStore

        steps = [
            Step(step_id="step_1", description="A", tool_hint="file"),
        ]
        states = engine._init_step_states(steps)
        context = ContextStore(task_id="task_1")

        result = engine._build_failure_result(
            Task(id="task_1", name="Test", goal="test", confidence=0.5),
            steps,
            states,
            context,
            "reason",
        )
        assert result.success is False


class TestRunTask:
    """TC-03-15-01 ~ TC-03-15-08: _run_task 集成测试"""

    @pytest.mark.asyncio
    async def test_run_task_validation_failure(self, engine):
        """TC-03-15-01: 步骤校验失败时直接返回（重复 ID）"""
        task = Task(
            id="task_1",
            name="Test",
            goal="test",
            confidence=0.5,
            steps=[
                Step(step_id="step_1", description="A", tool_hint="file"),
                Step(step_id="step_1", description="B", tool_hint="file"),
            ],
        )
        result = await engine.run(task)
        assert result.success is False
        assert "校验失败" in result.message or "重复" in result.message

    @pytest.mark.asyncio
    async def test_run_task_validation_missing_dep(self):
        """TC-03-15-02: 步骤校验失败（缺失依赖）"""
        engine = TaskEngine(
            llm_client=MockLLMClient(),
            max_total_steps=10,
            total_timeout=60,
            step_timeout=120,
            max_retries=3,
        )

        task = Task(
            id="task_1",
            name="Test",
            goal="test",
            confidence=0.5,
            steps=[
                Step(step_id="step_1", description="A", tool_hint="file", depends_on=["nonexistent"]),
            ],
        )
        result = await engine.run(task)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_run_task_guard_triggers(self):
        """TC-03-15-02: 预算保护触发时正确终止"""
        engine = TaskEngine(
            llm_client=MockLLMClient(),
            max_total_steps=0,  # 无预算
            total_timeout=1800,
            step_timeout=120,
            max_retries=3,
        )

        task = Task(
            id="task_1",
            name="Test",
            goal="test",
            confidence=0.5,
            steps=[
                Step(step_id="step_1", description="A", tool_hint="file"),
            ],
        )
        result = await engine.run(task)
        assert result.success is False
        assert "步骤" in result.message or "预算" in result.message or "无可执行" in result.message

    @pytest.mark.asyncio
    async def test_run_task_with_steps(self):
        """TC-03-15-03: 有步骤时进入主循环"""
        engine = TaskEngine(
            llm_client=MockLLMClient(),
            max_total_steps=10,
            total_timeout=60,
            step_timeout=120,
            max_retries=3,
        )

        task = Task(
            id="task_1",
            name="Test",
            goal="test",
            confidence=0.5,
            steps=[
                Step(step_id="step_1", description="A", tool_hint="file"),
            ],
        )
        result = await engine.run(task)
        # 由于 MockLLMClient.generate_tool_calls 返回空列表，执行会失败或阻塞
        assert result.task_id == "task_1"

    @pytest.mark.asyncio
    async def test_run_task_exception_handling(self):
        """TC-03-15-04: 主循环异常时正确捕获"""
        from unittest.mock import AsyncMock, patch

        engine = TaskEngine(
            llm_client=MockLLMClient(),
            max_total_steps=10,
            total_timeout=60,
            step_timeout=120,
            max_retries=3,
        )

        task = Task(
            id="task_1",
            name="Test",
            goal="test",
            confidence=0.5,
            steps=[
                Step(step_id="step_1", description="A", tool_hint="file"),
            ],
        )

        # Mock _main_loop to raise exception
        with patch.object(engine, "_main_loop", new_callable=AsyncMock) as mock_loop:
            mock_loop.side_effect = RuntimeError("测试异常")
            result = await engine.run(task)
            assert result.success is False
            assert "执行异常" in result.message


class TestMainLoop:
    """TC-03-15-09 ~ TC-03-15-20: _main_loop 主循环测试"""

    @pytest.mark.asyncio
    async def test_main_loop_guard_triggers_immediately(self, engine):
        """TC-03-15-09: Guard 立即触发时返回失败结果"""
        from yellowbull.agent.completion_evaluator import CompletionEvaluator
        from yellowbull.agent.executor import StepExecutor
        from yellowbull.agent.failure_handler import FailureHandler
        from yellowbull.agent.obstacle_resolver import ObstacleResolver
        from yellowbull.agent.step_selector import StepSelector

        steps = [Step(step_id="s1", description="A", tool_hint="file")]
        states = engine._init_step_states(steps)
        context = ContextStore(task_id="task_1")
        guard = BudgetGuard(max_total_steps=0, total_timeout=60, step_timeout=120)
        guard.start()

        executor = StepExecutor(context, MockLLMClient(), 120)
        selector = StepSelector(step_states=states)
        evaluator = CompletionEvaluator()
        obstacle_resolver = ObstacleResolver(llm_client=MockLLMClient())
        failure_handler = FailureHandler(
            step_selector=selector,
            obstacle_resolver=obstacle_resolver,
            max_retries=3,
        )

        task = Task(id="task_1", name="Test", goal="test", confidence=0.5)
        result = await engine._main_loop(
            task=task,
            steps=steps,
            step_states=states,
            context_store=context,
            guard=guard,
            executor=executor,
            selector=selector,
            evaluator=evaluator,
            failure_handler=failure_handler,
        )
        assert result.success is False

    @pytest.mark.asyncio
    async def test_main_loop_completion_immediate(self, engine):
        """TC-03-15-10: 完成评估立即返回时正确退出"""
        from yellowbull.agent.completion_evaluator import (
            CompletionEvaluator,
            CompletionResult,
        )
        from yellowbull.agent.executor import StepExecutor
        from yellowbull.agent.failure_handler import FailureHandler
        from yellowbull.agent.obstacle_resolver import ObstacleResolver
        from yellowbull.agent.step_selector import StepSelector

        steps = [Step(step_id="s1", description="A", tool_hint="file")]
        states = engine._init_step_states(steps)
        # 标记为已完成，使 evaluator 立即返回完成
        states["s1"].mark_done({})
        context = ContextStore(task_id="task_1")
        guard = BudgetGuard(max_total_steps=10, total_timeout=60, step_timeout=120)
        guard.start()

        executor = StepExecutor(context, MockLLMClient(), 120)
        selector = StepSelector(step_states=states)
        evaluator = CompletionEvaluator()
        obstacle_resolver = ObstacleResolver(llm_client=MockLLMClient())
        failure_handler = FailureHandler(
            step_selector=selector,
            obstacle_resolver=obstacle_resolver,
            max_retries=3,
        )

        task = Task(id="task_1", name="Test", goal="test", confidence=0.5)
        result = await engine._main_loop(
            task=task,
            steps=steps,
            step_states=states,
            context_store=context,
            guard=guard,
            executor=executor,
            selector=selector,
            evaluator=evaluator,
            failure_handler=failure_handler,
        )
        assert result.success is True  # 已完成

    @pytest.mark.asyncio
    async def test_main_loop_no_next_step(self):
        """TC-03-15-11: 无可执行步骤时返回阻塞结果"""
        from unittest.mock import MagicMock, AsyncMock
        from yellowbull.agent.completion_evaluator import (
            CompletionEvaluator,
            CompletionResult,
        )
        from yellowbull.agent.executor import StepExecutor
        from yellowbull.agent.failure_handler import FailureHandler
        from yellowbull.agent.obstacle_resolver import ObstacleResolver
        from yellowbull.agent.step_selector import StepSelector

        engine = TaskEngine(
            llm_client=MockLLMClient(),
            max_total_steps=10,
            total_timeout=60,
            step_timeout=120,
            max_retries=3,
        )

        steps = [Step(step_id="s1", description="A", tool_hint="file")]
        states = engine._init_step_states(steps)
        context = ContextStore(task_id="task_1")
        guard = BudgetGuard(max_total_steps=10, total_timeout=60, step_timeout=120)
        guard.start()

        executor = StepExecutor(context, MockLLMClient(), 120)
        selector = StepSelector(step_states=states)
        # 让 selector 返回 None（无可执行步骤）
        selector.get_next = MagicMock(return_value=None)
        evaluator = CompletionEvaluator()
        # 让 evaluator 返回未完成
        evaluator.evaluate = MagicMock(
            return_value=CompletionResult(
                is_complete=False,
                is_success=False,
                reason="未完成",
                done_steps=0,
                failed_steps=0,
                skipped_steps=0,
                completion_rate=0.0,
                critical_done=0,
                critical_total=0,
            )
        )
        obstacle_resolver = ObstacleResolver(llm_client=MockLLMClient())
        failure_handler = FailureHandler(
            step_selector=selector,
            obstacle_resolver=obstacle_resolver,
            max_retries=3,
        )

        task = Task(id="task_1", name="Test", goal="test", confidence=0.5)
        result = await engine._main_loop(
            task=task,
            steps=steps,
            step_states=states,
            context_store=context,
            guard=guard,
            executor=executor,
            selector=selector,
            evaluator=evaluator,
            failure_handler=failure_handler,
        )
        assert result.success is False
        assert "阻塞" in result.message or "无可执行" in result.message

    @pytest.mark.asyncio
    async def test_main_loop_normal_step_success(self):
        """TC-03-15-12: 普通步骤成功执行"""
        from unittest.mock import MagicMock, AsyncMock, patch
        from yellowbull.agent.completion_evaluator import (
            CompletionEvaluator,
            CompletionResult,
        )
        from yellowbull.agent.executor import StepExecutor, StepResultData
        from yellowbull.agent.failure_handler import FailureHandler
        from yellowbull.agent.obstacle_resolver import ObstacleResolver
        from yellowbull.agent.step_selector import StepSelector

        engine = TaskEngine(
            llm_client=MockLLMClient(),
            max_total_steps=10,
            total_timeout=60,
            step_timeout=120,
            max_retries=3,
        )

        steps = [Step(step_id="s1", description="A", tool_hint="file")]
        states = engine._init_step_states(steps)
        context = ContextStore(task_id="task_1")
        guard = BudgetGuard(max_total_steps=10, total_timeout=60, step_timeout=120)
        guard.start()

        executor = StepExecutor(context, MockLLMClient(), 120)
        # Mock execute to return success
        executor.execute = AsyncMock(
            return_value=StepResultData(
                step_id="s1",
                success=True,
                result={"output": "done"},
                error=None,
                tool_used="file",
                duration_ms=10,
            )
        )

        selector = StepSelector(step_states=states)
        evaluator = CompletionEvaluator()
        # First call: not complete, second call: complete
        call_count = [0]
        original_evaluate = evaluator.evaluate

        def mock_evaluate(steps, states):
            call_count[0] += 1
            if call_count[0] >= 2:
                return CompletionResult(
                    is_complete=True,
                    is_success=True,
                    reason="完成",
                    done_steps=1,
                    failed_steps=0,
                    skipped_steps=0,
                    completion_rate=1.0,
                    critical_done=1,
                    critical_total=1,
                )
            return CompletionResult(
                is_complete=False,
                is_success=False,
                reason="未完成",
                done_steps=0,
                failed_steps=0,
                skipped_steps=0,
                completion_rate=0.0,
                critical_done=0,
                critical_total=1,
            )

        evaluator.evaluate = mock_evaluate

        obstacle_resolver = ObstacleResolver(llm_client=MockLLMClient())
        failure_handler = FailureHandler(
            step_selector=selector,
            obstacle_resolver=obstacle_resolver,
            max_retries=3,
        )

        task = Task(id="task_1", name="Test", goal="test", confidence=0.5)
        result = await engine._main_loop(
            task=task,
            steps=steps,
            step_states=states,
            context_store=context,
            guard=guard,
            executor=executor,
            selector=selector,
            evaluator=evaluator,
            failure_handler=failure_handler,
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_main_loop_step_failure_retry(self):
        """TC-03-15-13: 步骤失败后重试"""
        from unittest.mock import MagicMock, AsyncMock
        from yellowbull.agent.completion_evaluator import (
            CompletionEvaluator,
            CompletionResult,
        )
        from yellowbull.agent.executor import StepExecutor, StepResultData
        from yellowbull.agent.failure_handler import FailureHandler
        from yellowbull.agent.obstacle_resolver import ObstacleResolver
        from yellowbull.agent.step_selector import StepSelector

        engine = TaskEngine(
            llm_client=MockLLMClient(),
            max_total_steps=10,
            total_timeout=60,
            step_timeout=120,
            max_retries=3,
        )

        steps = [Step(step_id="s1", description="A", tool_hint="file")]
        states = engine._init_step_states(steps)
        context = ContextStore(task_id="task_1")
        guard = BudgetGuard(max_total_steps=10, total_timeout=60, step_timeout=120)
        guard.start()

        executor = StepExecutor(context, MockLLMClient(), 120)
        # First call fails, second succeeds
        call_count = [0]

        async def mock_execute(step):
            call_count[0] += 1
            if call_count[0] == 1:
                return StepResultData(
                    step_id="s1",
                    success=False,
                    result=None,
                    error="临时错误",
                    tool_used="file",
                    duration_ms=10,
                )
            return StepResultData(
                step_id="s1",
                success=True,
                result={"output": "done"},
                error=None,
                tool_used="file",
                duration_ms=10,
            )

        executor.execute = mock_execute

        selector = StepSelector(step_states=states)
        evaluator = CompletionEvaluator()

        eval_count = [0]
        def mock_evaluate(steps, states):
            eval_count[0] += 1
            if eval_count[0] >= 3:
                return CompletionResult(
                    is_complete=True,
                    is_success=True,
                    reason="完成",
                    done_steps=1,
                    failed_steps=0,
                    skipped_steps=0,
                    completion_rate=1.0,
                    critical_done=1,
                    critical_total=1,
                )
            return CompletionResult(
                is_complete=False,
                is_success=False,
                reason="未完成",
                done_steps=0,
                failed_steps=0,
                skipped_steps=0,
                completion_rate=0.0,
                critical_done=0,
                critical_total=1,
            )

        evaluator.evaluate = mock_evaluate

        obstacle_resolver = ObstacleResolver(llm_client=MockLLMClient())
        failure_handler = FailureHandler(
            step_selector=selector,
            obstacle_resolver=obstacle_resolver,
            max_retries=3,
        )
        # Mock handle_failure to return "retry"
        failure_handler.handle_failure = AsyncMock(return_value="retry")

        task = Task(id="task_1", name="Test", goal="test", confidence=0.5)
        result = await engine._main_loop(
            task=task,
            steps=steps,
            step_states=states,
            context_store=context,
            guard=guard,
            executor=executor,
            selector=selector,
            evaluator=evaluator,
            failure_handler=failure_handler,
        )
        # 重试后应该成功
        assert result.success is True

    @pytest.mark.asyncio
    async def test_main_loop_step_failure_abort(self):
        """TC-03-15-14: 关键步骤失败时终止任务"""
        from unittest.mock import MagicMock, AsyncMock
        from yellowbull.agent.completion_evaluator import (
            CompletionEvaluator,
            CompletionResult,
        )
        from yellowbull.agent.executor import StepExecutor, StepResultData
        from yellowbull.agent.failure_handler import FailureHandler
        from yellowbull.agent.obstacle_resolver import ObstacleResolver
        from yellowbull.agent.step_selector import StepSelector

        engine = TaskEngine(
            llm_client=MockLLMClient(),
            max_total_steps=10,
            total_timeout=60,
            step_timeout=120,
            max_retries=3,
        )

        steps = [Step(step_id="s1", description="A", tool_hint="file", is_critical=True)]
        states = engine._init_step_states(steps)
        context = ContextStore(task_id="task_1")
        guard = BudgetGuard(max_total_steps=10, total_timeout=60, step_timeout=120)
        guard.start()

        executor = StepExecutor(context, MockLLMClient(), 120)
        executor.execute = AsyncMock(
            return_value=StepResultData(
                step_id="s1",
                success=False,
                result=None,
                error="关键错误",
                tool_used="file",
                duration_ms=10,
            )
        )

        selector = StepSelector(step_states=states)
        evaluator = CompletionEvaluator()
        evaluator.evaluate = MagicMock(
            return_value=CompletionResult(
                is_complete=False,
                is_success=False,
                reason="未完成",
                done_steps=0,
                failed_steps=0,
                skipped_steps=0,
                completion_rate=0.0,
                critical_done=0,
                critical_total=1,
            )
        )

        obstacle_resolver = ObstacleResolver(llm_client=MockLLMClient())
        failure_handler = FailureHandler(
            step_selector=selector,
            obstacle_resolver=obstacle_resolver,
            max_retries=3,
        )
        # Mock handle_failure to return "abort"
        failure_handler.handle_failure = AsyncMock(return_value="abort")

        task = Task(id="task_1", name="Test", goal="test", confidence=0.5)
        result = await engine._main_loop(
            task=task,
            steps=steps,
            step_states=states,
            context_store=context,
            guard=guard,
            executor=executor,
            selector=selector,
            evaluator=evaluator,
            failure_handler=failure_handler,
        )
        assert result.success is False

    @pytest.mark.asyncio
    async def test_main_loop_step_failure_skip(self):
        """TC-03-15-15: 非关键步骤失败时跳过"""
        from unittest.mock import MagicMock, AsyncMock
        from yellowbull.agent.completion_evaluator import (
            CompletionEvaluator,
            CompletionResult,
        )
        from yellowbull.agent.executor import StepExecutor, StepResultData
        from yellowbull.agent.failure_handler import FailureHandler
        from yellowbull.agent.obstacle_resolver import ObstacleResolver
        from yellowbull.agent.step_selector import StepSelector

        engine = TaskEngine(
            llm_client=MockLLMClient(),
            max_total_steps=10,
            total_timeout=60,
            step_timeout=120,
            max_retries=3,
        )

        steps = [Step(step_id="s1", description="A", tool_hint="file")]
        states = engine._init_step_states(steps)
        context = ContextStore(task_id="task_1")
        guard = BudgetGuard(max_total_steps=10, total_timeout=60, step_timeout=120)
        guard.start()

        executor = StepExecutor(context, MockLLMClient(), 120)
        executor.execute = AsyncMock(
            return_value=StepResultData(
                step_id="s1",
                success=False,
                result=None,
                error="非关键错误",
                tool_used="file",
                duration_ms=10,
            )
        )

        selector = StepSelector(step_states=states)
        evaluator = CompletionEvaluator()

        eval_count = [0]
        def mock_evaluate(steps, states):
            eval_count[0] += 1
            if eval_count[0] >= 2:
                return CompletionResult(
                    is_complete=True,
                    is_success=False,
                    reason="部分完成",
                    done_steps=0,
                    failed_steps=0,
                    skipped_steps=1,
                    completion_rate=0.0,
                    critical_done=0,
                    critical_total=0,
                )
            return CompletionResult(
                is_complete=False,
                is_success=False,
                reason="未完成",
                done_steps=0,
                failed_steps=0,
                skipped_steps=0,
                completion_rate=0.0,
                critical_done=0,
                critical_total=0,
            )

        evaluator.evaluate = mock_evaluate

        obstacle_resolver = ObstacleResolver(llm_client=MockLLMClient())
        failure_handler = FailureHandler(
            step_selector=selector,
            obstacle_resolver=obstacle_resolver,
            max_retries=3,
        )
        # Mock handle_failure to return "skip"
        failure_handler.handle_failure = AsyncMock(return_value="skip")

        task = Task(id="task_1", name="Test", goal="test", confidence=0.5)
        result = await engine._main_loop(
            task=task,
            steps=steps,
            step_states=states,
            context_store=context,
            guard=guard,
            executor=executor,
            selector=selector,
            evaluator=evaluator,
            failure_handler=failure_handler,
        )
        # 跳过步骤后任务完成（部分成功）
        assert result.steps_skipped >= 1 or not result.success

    @pytest.mark.asyncio
    async def test_main_loop_branch_step(self):
        """TC-03-15-16: 分支步骤执行（条件满足）"""
        from unittest.mock import MagicMock, AsyncMock
        from yellowbull.agent.completion_evaluator import (
            CompletionEvaluator,
            CompletionResult,
        )
        from yellowbull.agent.executor import StepExecutor, BranchResult
        from yellowbull.agent.failure_handler import FailureHandler
        from yellowbull.agent.obstacle_resolver import ObstacleResolver
        from yellowbull.agent.step_selector import StepSelector

        engine = TaskEngine(
            llm_client=MockLLMClient(),
            max_total_steps=10,
            total_timeout=60,
            step_timeout=120,
            max_retries=3,
        )

        steps = [
            Step(step_id="s1", description="分支", tool_hint="file", is_branch_point=True),
        ]
        states = engine._init_step_states(steps)
        context = ContextStore(task_id="task_1")
        guard = BudgetGuard(max_total_steps=10, total_timeout=60, step_timeout=120)
        guard.start()

        executor = StepExecutor(context, MockLLMClient(), 120)
        executor.execute_branch = AsyncMock(
            return_value=BranchResult(
                condition_met=True,
                activated_steps=["s1"],
                skipped_steps=[],
            )
        )

        selector = StepSelector(step_states=states)
        evaluator = CompletionEvaluator()

        eval_count = [0]
        def mock_evaluate(steps, states):
            eval_count[0] += 1
            if eval_count[0] >= 2:
                return CompletionResult(
                    is_complete=True,
                    is_success=True,
                    reason="完成",
                    done_steps=1,
                    failed_steps=0,
                    skipped_steps=0,
                    completion_rate=1.0,
                    critical_done=1,
                    critical_total=1,
                )
            return CompletionResult(
                is_complete=False,
                is_success=False,
                reason="未完成",
                done_steps=0,
                failed_steps=0,
                skipped_steps=0,
                completion_rate=0.0,
                critical_done=0,
                critical_total=1,
            )

        evaluator.evaluate = mock_evaluate

        obstacle_resolver = ObstacleResolver(llm_client=MockLLMClient())
        failure_handler = FailureHandler(
            step_selector=selector,
            obstacle_resolver=obstacle_resolver,
            max_retries=3,
        )

        task = Task(id="task_1", name="Test", goal="test", confidence=0.5)
        result = await engine._main_loop(
            task=task,
            steps=steps,
            step_states=states,
            context_store=context,
            guard=guard,
            executor=executor,
            selector=selector,
            evaluator=evaluator,
            failure_handler=failure_handler,
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_main_loop_branch_condition_not_met(self):
        """TC-03-15-16b: 分支条件不满足时跳过步骤（覆盖 line 206 + 210-212）"""
        from unittest.mock import MagicMock, AsyncMock
        from yellowbull.agent.completion_evaluator import (
            CompletionEvaluator,
            CompletionResult,
        )
        from yellowbull.agent.executor import StepExecutor, BranchResult
        from yellowbull.agent.failure_handler import FailureHandler
        from yellowbull.agent.obstacle_resolver import ObstacleResolver
        from yellowbull.agent.step_selector import StepSelector

        engine = TaskEngine(
            llm_client=MockLLMClient(),
            max_total_steps=10,
            total_timeout=60,
            step_timeout=120,
            max_retries=3,
        )

        steps = [
            Step(step_id="s1", description="分支", tool_hint="file", is_branch_point=True),
            Step(step_id="s2", description="被跳过", tool_hint="file"),
        ]
        states = engine._init_step_states(steps)
        context = ContextStore(task_id="task_1")
        guard = BudgetGuard(max_total_steps=10, total_timeout=60, step_timeout=120)
        guard.start()

        executor = StepExecutor(context, MockLLMClient(), 120)
        # condition_met=False → mark_done(skipped_steps) + mark_skipped(by_branch=True)
        executor.execute_branch = AsyncMock(
            return_value=BranchResult(
                condition_met=False,
                activated_steps=[],
                skipped_steps=["s1", "s2"],
            )
        )

        selector = StepSelector(step_states=states)
        evaluator = CompletionEvaluator()

        eval_count = [0]
        def mock_evaluate(steps, states):
            eval_count[0] += 1
            if eval_count[0] >= 2:
                return CompletionResult(
                    is_complete=True,
                    is_success=True,
                    reason="完成",
                    done_steps=0,
                    failed_steps=0,
                    skipped_steps=2,
                    completion_rate=0.0,
                    critical_done=0,
                    critical_total=0,
                )
            return CompletionResult(
                is_complete=False,
                is_success=False,
                reason="未完成",
                done_steps=0,
                failed_steps=0,
                skipped_steps=0,
                completion_rate=0.0,
                critical_done=0,
                critical_total=1,
            )

        evaluator.evaluate = mock_evaluate

        obstacle_resolver = ObstacleResolver(llm_client=MockLLMClient())
        failure_handler = FailureHandler(
            step_selector=selector,
            obstacle_resolver=obstacle_resolver,
            max_retries=3,
        )

        task = Task(id="task_1", name="Test", goal="test", confidence=0.5)
        result = await engine._main_loop(
            task=task,
            steps=steps,
            step_states=states,
            context_store=context,
            guard=guard,
            executor=executor,
            selector=selector,
            evaluator=evaluator,
            failure_handler=failure_handler,
        )
        assert result.success is True
        # Verify skipped steps were marked by branch
        assert states["s1"].status != StepStatus.PENDING

    @pytest.mark.asyncio
    async def test_main_loop_loop_step(self):
        """TC-03-15-17: 循环步骤执行（全部成功）"""
        from unittest.mock import MagicMock, AsyncMock
        from yellowbull.agent.completion_evaluator import (
            CompletionEvaluator,
            CompletionResult,
        )
        from yellowbull.agent.executor import StepExecutor, LoopResult
        from yellowbull.agent.failure_handler import FailureHandler
        from yellowbull.agent.obstacle_resolver import ObstacleResolver
        from yellowbull.agent.step_selector import StepSelector

        engine = TaskEngine(
            llm_client=MockLLMClient(),
            max_total_steps=10,
            total_timeout=60,
            step_timeout=120,
            max_retries=3,
        )

        steps = [
            Step(step_id="s1", description="循环", tool_hint="file", is_loop=True),
        ]
        states = engine._init_step_states(steps)
        context = ContextStore(task_id="task_1")
        guard = BudgetGuard(max_total_steps=10, total_timeout=60, step_timeout=120)
        guard.start()

        executor = StepExecutor(context, MockLLMClient(), 120)
        executor.execute_loop = AsyncMock(
            return_value=LoopResult(
                iterations=3,
                success_count=3,
                failed_count=0,
                results=[{}, {}, {}],
            )
        )

        selector = StepSelector(step_states=states)
        evaluator = CompletionEvaluator()

        eval_count = [0]
        def mock_evaluate(steps, states):
            eval_count[0] += 1
            if eval_count[0] >= 2:
                return CompletionResult(
                    is_complete=True,
                    is_success=True,
                    reason="完成",
                    done_steps=1,
                    failed_steps=0,
                    skipped_steps=0,
                    completion_rate=1.0,
                    critical_done=1,
                    critical_total=1,
                )
            return CompletionResult(
                is_complete=False,
                is_success=False,
                reason="未完成",
                done_steps=0,
                failed_steps=0,
                skipped_steps=0,
                completion_rate=0.0,
                critical_done=0,
                critical_total=1,
            )

        evaluator.evaluate = mock_evaluate

        obstacle_resolver = ObstacleResolver(llm_client=MockLLMClient())
        failure_handler = FailureHandler(
            step_selector=selector,
            obstacle_resolver=obstacle_resolver,
            max_retries=3,
        )

        task = Task(id="task_1", name="Test", goal="test", confidence=0.5)
        result = await engine._main_loop(
            task=task,
            steps=steps,
            step_states=states,
            context_store=context,
            guard=guard,
            executor=executor,
            selector=selector,
            evaluator=evaluator,
            failure_handler=failure_handler,
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_main_loop_loop_with_failures(self):
        """TC-03-15-17b: 循环步骤部分失败时标记失败（覆盖 line 222）"""
        from unittest.mock import MagicMock, AsyncMock
        from yellowbull.agent.completion_evaluator import (
            CompletionEvaluator,
            CompletionResult,
        )
        from yellowbull.agent.executor import StepExecutor, LoopResult
        from yellowbull.agent.failure_handler import FailureHandler
        from yellowbull.agent.obstacle_resolver import ObstacleResolver
        from yellowbull.agent.step_selector import StepSelector

        engine = TaskEngine(
            llm_client=MockLLMClient(),
            max_total_steps=10,
            total_timeout=60,
            step_timeout=120,
            max_retries=3,
        )

        steps = [
            Step(step_id="s1", description="循环", tool_hint="file", is_loop=True),
        ]
        states = engine._init_step_states(steps)
        context = ContextStore(task_id="task_1")
        guard = BudgetGuard(max_total_steps=10, total_timeout=60, step_timeout=120)
        guard.start()

        executor = StepExecutor(context, MockLLMClient(), 120)
        # failed_count > 0 → mark_failed (line 222)
        executor.execute_loop = AsyncMock(
            return_value=LoopResult(
                iterations=3,
                success_count=2,
                failed_count=1,
                results=[{}, {}, {}],
            )
        )

        selector = StepSelector(step_states=states)
        evaluator = CompletionEvaluator()

        eval_count = [0]
        def mock_evaluate(steps, states):
            eval_count[0] += 1
            if eval_count[0] >= 2:
                return CompletionResult(
                    is_complete=True,
                    is_success=False,
                    reason="部分完成",
                    done_steps=0,
                    failed_steps=1,
                    skipped_steps=0,
                    completion_rate=0.0,
                    critical_done=0,
                    critical_total=1,
                )
            return CompletionResult(
                is_complete=False,
                is_success=False,
                reason="未完成",
                done_steps=0,
                failed_steps=0,
                skipped_steps=0,
                completion_rate=0.0,
                critical_done=0,
                critical_total=1,
            )

        evaluator.evaluate = mock_evaluate

        obstacle_resolver = ObstacleResolver(llm_client=MockLLMClient())
        failure_handler = FailureHandler(
            step_selector=selector,
            obstacle_resolver=obstacle_resolver,
            max_retries=3,
        )

        task = Task(id="task_1", name="Test", goal="test", confidence=0.5)
        result = await engine._main_loop(
            task=task,
            steps=steps,
            step_states=states,
            context_store=context,
            guard=guard,
            executor=executor,
            selector=selector,
            evaluator=evaluator,
            failure_handler=failure_handler,
        )
        # Loop with failures should mark the step as failed
        assert states["s1"].status == StepStatus.FAILED

    @pytest.mark.asyncio
    async def test_main_loop_step_exception(self):
        """TC-03-15-18: 步骤执行异常时正确处理"""
        from unittest.mock import MagicMock, AsyncMock
        from yellowbull.agent.completion_evaluator import (
            CompletionEvaluator,
            CompletionResult,
        )
        from yellowbull.agent.executor import StepExecutor
        from yellowbull.agent.failure_handler import FailureHandler
        from yellowbull.agent.obstacle_resolver import ObstacleResolver
        from yellowbull.agent.step_selector import StepSelector

        engine = TaskEngine(
            llm_client=MockLLMClient(),
            max_total_steps=10,
            total_timeout=60,
            step_timeout=120,
            max_retries=3,
        )

        steps = [Step(step_id="s1", description="A", tool_hint="file")]
        states = engine._init_step_states(steps)
        context = ContextStore(task_id="task_1")
        guard = BudgetGuard(max_total_steps=10, total_timeout=60, step_timeout=120)
        guard.start()

        executor = StepExecutor(context, MockLLMClient(), 120)
        # Mock execute to raise exception
        executor.execute = AsyncMock(side_effect=RuntimeError("执行异常"))

        selector = StepSelector(step_states=states)
        evaluator = CompletionEvaluator()

        eval_count = [0]
        def mock_evaluate(steps, states):
            eval_count[0] += 1
            if eval_count[0] >= 2:
                return CompletionResult(
                    is_complete=True,
                    is_success=False,
                    reason="异常完成",
                    done_steps=0,
                    failed_steps=1,
                    skipped_steps=0,
                    completion_rate=0.0,
                    critical_done=0,
                    critical_total=1,
                )
            return CompletionResult(
                is_complete=False,
                is_success=False,
                reason="未完成",
                done_steps=0,
                failed_steps=0,
                skipped_steps=0,
                completion_rate=0.0,
                critical_done=0,
                critical_total=1,
            )

        evaluator.evaluate = mock_evaluate

        obstacle_resolver = ObstacleResolver(llm_client=MockLLMClient())
        failure_handler = FailureHandler(
            step_selector=selector,
            obstacle_resolver=obstacle_resolver,
            max_retries=3,
        )
        failure_handler.handle_failure = AsyncMock(return_value="skip")

        task = Task(id="task_1", name="Test", goal="test", confidence=0.5)
        result = await engine._main_loop(
            task=task,
            steps=steps,
            step_states=states,
            context_store=context,
            guard=guard,
            executor=executor,
            selector=selector,
            evaluator=evaluator,
            failure_handler=failure_handler,
        )
        # 异常被捕获，步骤标记为失败
        assert states["s1"].status.value in ["failed", "skipped"]


class TestBuildFailureResultExtended:
    """TC-03-15-19 ~ TC-03-15-22: _build_failure_result 测试"""

    def test_build_failure_result_with_skipped(self, engine):
        """TC-03-15-19: 包含跳过步骤的失败结果"""
        from yellowbull.agent.step_state import ContextStore

        steps = [
            Step(step_id="s1", description="A", tool_hint="file"),
            Step(step_id="s2", description="B", tool_hint="file"),
            Step(step_id="s3", description="C", tool_hint="file"),
        ]
        states = engine._init_step_states(steps)
        states["s1"].mark_done({})
        states["s2"].mark_failed("error")
        states["s3"].mark_skipped(by_branch=True)
        context = ContextStore(task_id="task_1")

        result = engine._build_failure_result(
            Task(id="task_1", name="Test", goal="test", confidence=0.5),
            steps,
            states,
            context,
            "测试失败",
        )
        assert result.steps_executed == 1
        assert result.steps_failed == 1
        assert result.steps_skipped == 1

    def test_build_failure_result_all_done(self, engine):
        """TC-03-15-20: 全部完成时的失败结果（用于验证计数）"""
        from yellowbull.agent.step_state import ContextStore

        steps = [
            Step(step_id="s1", description="A", tool_hint="file"),
            Step(step_id="s2", description="B", tool_hint="file"),
        ]
        states = engine._init_step_states(steps)
        states["s1"].mark_done({})
        states["s2"].mark_done({})
        context = ContextStore(task_id="task_1")

        result = engine._build_failure_result(
            Task(id="task_1", name="Test", goal="test", confidence=0.5),
            steps,
            states,
            context,
            "测试失败",
        )
        assert result.steps_executed == 2
        assert result.steps_failed == 0
        assert result.success is False
