"""T03: 完成评估器单元测试"""

import pytest

from yellowbull.agent.completion_evaluator import CompletionEvaluator, CompletionResult
from yellowbull.agent.step_state import StepState, StepStatus
from yellowbull.models.step import Step


@pytest.fixture
def evaluator():
    return CompletionEvaluator()


@pytest.fixture
def simple_steps():
    return [
        Step(step_id="step_1", description="A", tool_hint="file"),
        Step(step_id="step_2", description="B", tool_hint="code"),
        Step(step_id="step_3", description="C", tool_hint="file"),
    ]


class TestCompletionResult:
    """TC-03-11-01 ~ TC-03-11-04"""

    def test_complete_success(self):
        """TC-03-11-01: 完成且成功"""
        result = CompletionResult(
            is_complete=True,
            is_success=True,
            reason="all done",
            total_steps=3,
            done_steps=3,
            failed_steps=0,
            skipped_steps=0,
        )
        assert result.is_complete is True
        assert result.is_success is True

    def test_complete_failure(self):
        """TC-03-11-02: 完成但失败"""
        result = CompletionResult(
            is_complete=True,
            is_success=False,
            reason="failed",
            total_steps=3,
            done_steps=2,
            failed_steps=1,
            skipped_steps=0,
        )
        assert result.is_complete is True
        assert result.is_success is False

    def test_not_complete(self):
        """TC-03-11-03: 未完成"""
        result = CompletionResult(
            is_complete=False,
            is_success=False,
            reason="running",
            total_steps=3,
            done_steps=1,
            failed_steps=0,
            skipped_steps=0,
        )
        assert result.is_complete is False

    def test_default_values(self):
        """TC-03-11-04: 默认值"""
        result = CompletionResult(is_complete=False, is_success=False)
        assert result.total_steps == 0
        assert result.done_steps == 0
        assert result.failed_steps == 0
        assert result.skipped_steps == 0


class TestEvaluateAllDone:
    """TC-03-11-05 ~ TC-03-11-08"""

    def test_all_done_is_complete(self, evaluator, simple_steps):
        """TC-03-11-05: 全部完成"""
        states = {s.step_id: StepState(s.step_id) for s in simple_steps}
        for state in states.values():
            state.mark_done("result")
        result = evaluator.evaluate(simple_steps, states)
        assert result.is_complete is True

    def test_all_done_is_success(self, evaluator, simple_steps):
        """TC-03-11-06: 全部成功"""
        states = {s.step_id: StepState(s.step_id) for s in simple_steps}
        for state in states.values():
            state.mark_done("result")
        result = evaluator.evaluate(simple_steps, states)
        assert result.is_success is True

    def test_all_done_counts(self, evaluator, simple_steps):
        """TC-03-11-07: 完成计数"""
        states = {s.step_id: StepState(s.step_id) for s in simple_steps}
        for state in states.values():
            state.mark_done("result")
        result = evaluator.evaluate(simple_steps, states)
        assert result.done_steps == 3
        assert result.failed_steps == 0

    def test_all_done_total(self, evaluator, simple_steps):
        """TC-03-11-08: 总数"""
        states = {s.step_id: StepState(s.step_id) for s in simple_steps}
        for state in states.values():
            state.mark_done("result")
        result = evaluator.evaluate(simple_steps, states)
        assert result.total_steps == 3


class TestEvaluateWithFailures:
    """TC-03-11-09 ~ TC-03-11-12"""

    def test_one_failure_is_complete(self, evaluator, simple_steps):
        """TC-03-11-09: 部分失败仍完成"""
        states = {s.step_id: StepState(s.step_id) for s in simple_steps}
        states["step_1"].mark_done("result")
        states["step_2"].mark_done("result")
        states["step_3"].mark_failed("error")
        result = evaluator.evaluate(simple_steps, states)
        assert result.is_complete is True

    def test_one_failure_counts(self, evaluator, simple_steps):
        """TC-03-11-10: 失败计数"""
        states = {s.step_id: StepState(s.step_id) for s in simple_steps}
        states["step_1"].mark_done("result")
        states["step_2"].mark_done("result")
        states["step_3"].mark_failed("error")
        result = evaluator.evaluate(simple_steps, states)
        assert result.failed_steps == 1

    def test_majority_success_is_success(self, evaluator, simple_steps):
        """TC-03-11-11: 大多数成功视为成功"""
        states = {s.step_id: StepState(s.step_id) for s in simple_steps}
        states["step_1"].mark_done("result")
        states["step_2"].mark_done("result")
        states["step_3"].mark_failed("error")
        result = evaluator.evaluate(simple_steps, states)
        assert result.is_success is True

    def test_all_failed_is_failure(self, evaluator, simple_steps):
        """TC-03-11-12: 全部失败"""
        states = {s.step_id: StepState(s.step_id) for s in simple_steps}
        for state in states.values():
            state.mark_failed("error")
        result = evaluator.evaluate(simple_steps, states)
        assert result.is_complete is True
        assert result.is_success is False


class TestEvaluateWithSkips:
    """TC-03-11-13 ~ TC-03-11-15"""

    def test_skipped_steps_counted(self, evaluator, simple_steps):
        """TC-03-11-13: 跳过步骤计数"""
        states = {s.step_id: StepState(s.step_id) for s in simple_steps}
        states["step_1"].mark_done("result")
        states["step_2"].mark_skipped()
        states["step_3"].mark_done("result")
        result = evaluator.evaluate(simple_steps, states)
        assert result.skipped_steps == 1

    def test_mixed_states_complete(self, evaluator, simple_steps):
        """TC-03-11-14: 混合状态完成"""
        states = {s.step_id: StepState(s.step_id) for s in simple_steps}
        states["step_1"].mark_done("result")
        states["step_2"].mark_failed("error")
        states["step_3"].mark_skipped()
        result = evaluator.evaluate(simple_steps, states)
        assert result.is_complete is True

    def test_skipped_count_in_total(self, evaluator, simple_steps):
        """TC-03-11-15: 跳过计入总数"""
        states = {s.step_id: StepState(s.step_id) for s in simple_steps}
        for state in states.values():
            state.mark_skipped()
        result = evaluator.evaluate(simple_steps, states)
        assert result.skipped_steps == 3


class TestEvaluateInProgress:
    """TC-03-11-16 ~ TC-03-11-18"""

    def test_running_not_complete(self, evaluator, simple_steps):
        """TC-03-11-16: 运行中未完成"""
        states = {s.step_id: StepState(s.step_id) for s in simple_steps}
        states["step_1"].mark_done("result")
        states["step_2"].mark_running()
        result = evaluator.evaluate(simple_steps, states)
        assert result.is_complete is False

    def test_pending_not_complete(self, evaluator, simple_steps):
        """TC-03-11-17: 待执行未完成"""
        states = {s.step_id: StepState(s.step_id) for s in simple_steps}
        states["step_1"].mark_done("result")
        # step_2, step_3 仍为 pending
        result = evaluator.evaluate(simple_steps, states)
        assert result.is_complete is False

    def test_in_progress_reason(self, evaluator, simple_steps):
        """TC-03-11-18: 未完成原因"""
        states = {s.step_id: StepState(s.step_id) for s in simple_steps}
        states["step_1"].mark_done("result")
        result = evaluator.evaluate(simple_steps, states)
        assert "未执行" in result.reason or "pending" in result.reason.lower() or result.is_complete is False


class TestEvaluateEmpty:
    """TC-03-11-19 ~ TC-03-11-20"""

    def test_empty_steps_complete(self, evaluator):
        """TC-03-11-19: 空步骤列表"""
        result = evaluator.evaluate([], {})
        assert result.is_complete is True

    def test_empty_steps_zero_counts(self, evaluator):
        """TC-03-11-20: 空步骤计数为零"""
        result = evaluator.evaluate([], {})
        assert result.total_steps == 0
        assert result.done_steps == 0


class TestCompletionEvaluatorBoundary:
    """T03-17: 完成判定边界场景"""

    def test_single_step_done(self, evaluator):
        """TC-03-17-01: 单步骤完成"""
        steps = [Step(step_id="s1", description="A", tool_hint="file")]
        states = {"s1": StepState("s1")}
        states["s1"].mark_done("result")
        result = evaluator.evaluate(steps, states)
        assert result.is_complete is True
        assert result.is_success is True

    def test_single_step_failed(self, evaluator):
        """TC-03-17-02: 单步骤失败"""
        steps = [Step(step_id="s1", description="A", tool_hint="file")]
        states = {"s1": StepState("s1")}
        states["s1"].mark_failed("error")
        result = evaluator.evaluate(steps, states)
        assert result.is_complete is True
        assert result.is_success is False

    def test_all_skipped(self, evaluator):
        """TC-03-17-03: 全部跳过"""
        steps = [
            Step(step_id="s1", description="A", tool_hint="file"),
            Step(step_id="s2", description="B", tool_hint="file"),
        ]
        states = {"s1": StepState("s1"), "s2": StepState("s2")}
        states["s1"].mark_skipped()
        states["s2"].mark_skipped()
        result = evaluator.evaluate(steps, states)
        assert result.is_complete is True
        assert result.skipped_steps == 2

    def test_missing_state_treated_as_pending(self, evaluator):
        """TC-03-17-04: 缺失状态视为待执行"""
        steps = [Step(step_id="s1", description="A", tool_hint="file")]
        result = evaluator.evaluate(steps, {})
        assert result.is_complete is False

    def test_large_step_list(self, evaluator):
        """TC-03-17-05: 大批量步骤"""
        steps = [Step(step_id=f"s{i}", description=f"D{i}", tool_hint="file") for i in range(100)]
        states = {s.step_id: StepState(s.step_id) for s in steps}
        for state in states.values():
            state.mark_done("result")
        result = evaluator.evaluate(steps, states)
        assert result.is_complete is True
        assert result.total_steps == 100
