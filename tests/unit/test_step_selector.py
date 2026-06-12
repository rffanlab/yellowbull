"""T03: 步骤选择器单元测试"""

import pytest

from yellowbull.agent.step_selector import StepSelector
from yellowbull.agent.step_state import StepState, StepStatus
from yellowbull.models.step import Step


@pytest.fixture
def step_states():
    steps = [
        Step(step_id="step_1", description="A", tool_hint="file"),
        Step(step_id="step_2", description="B", tool_hint="code", depends_on=["step_1"]),
        Step(step_id="step_3", description="C", tool_hint="file", depends_on=["step_2"]),
        Step(step_id="step_4", description="D", tool_hint="shell"),
    ]
    return {step.step_id: StepState(step.step_id) for step in steps}


@pytest.fixture
def steps():
    return [
        Step(step_id="step_1", description="A", tool_hint="file"),
        Step(step_id="step_2", description="B", tool_hint="code", depends_on=["step_1"]),
        Step(step_id="step_3", description="C", tool_hint="file", depends_on=["step_2"]),
        Step(step_id="step_4", description="D", tool_hint="shell"),
    ]


class TestGetNext:
    """TC-03-04-01 ~ TC-03-04-05"""

    def test_select_first_pending(self, step_states, steps):
        """TC-03-04-01: 选择第一个 pending 步骤"""
        selector = StepSelector(step_states)
        next_step = selector.get_next(steps)
        assert next_step is not None

    def test_skip_running_steps(self, step_states, steps):
        """TC-03-04-02: 跳过 running 步骤"""
        step_states["step_1"].mark_running()
        selector = StepSelector(step_states)
        next_step = selector.get_next(steps)
        assert next_step.step_id != "step_1"

    def test_skip_done_steps(self, step_states, steps):
        """TC-03-04-03: 跳过 done 步骤"""
        step_states["step_1"].mark_done("result")
        selector = StepSelector(step_states)
        next_step = selector.get_next(steps)
        assert next_step.step_id != "step_1"

    def test_skip_failed_steps(self, step_states, steps):
        """TC-03-04-04: 跳过 failed 步骤"""
        step_states["step_1"].mark_failed("error")
        selector = StepSelector(step_states)
        next_step = selector.get_next(steps)
        assert next_step.step_id != "step_1"

    def test_skip_skipped_steps(self, step_states, steps):
        """TC-03-04-05: 跳过 skipped 步骤"""
        step_states["step_1"].mark_skipped()
        selector = StepSelector(step_states)
        next_step = selector.get_next(steps)
        assert next_step.step_id != "step_1"


class TestDependencyCheck:
    """TC-03-04-06 ~ TC-03-04-09"""

    def test_dependent_step_not_selected(self, step_states, steps):
        """TC-03-04-06: 依赖未满足时不选择"""
        selector = StepSelector(step_states)
        next_step = selector.get_next(steps)
        # step_2 依赖 step_1，step_1 未完成
        assert next_step.step_id != "step_2"

    def test_dependent_step_selected_after_done(self, step_states, steps):
        """TC-03-04-07: 依赖完成后可以选择"""
        step_states["step_1"].mark_done("result")
        selector = StepSelector(step_states)
        next_step = selector.get_next(steps)
        assert next_step.step_id == "step_2"

    def test_dependent_step_selected_after_skipped(self, step_states, steps):
        """TC-03-04-08: 依赖跳过时可以选择"""
        step_states["step_1"].mark_skipped()
        selector = StepSelector(step_states)
        next_step = selector.get_next(steps)
        # step_2 的依赖被跳过，应该可以选择
        assert next_step.step_id == "step_2"

    def test_no_available_steps(self, step_states, steps):
        """TC-03-04-09: 无可执行步骤返回 None"""
        for state in step_states.values():
            state.mark_done("result")
        selector = StepSelector(step_states)
        next_step = selector.get_next(steps)
        assert next_step is None


class TestCascadeSkip:
    """TC-03-04-10 ~ TC-03-04-12"""

    def test_cascade_skip_dependents(self, step_states, steps):
        """TC-03-04-10: 级联跳过依赖步骤"""
        selector = StepSelector(step_states)
        skipped = selector._cascade_skip(steps, "step_1")
        assert "step_2" in skipped

    def test_cascade_skip_chain(self, step_states, steps):
        """TC-03-04-11: 级联跳过链"""
        selector = StepSelector(step_states)
        skipped = selector._cascade_skip(steps, "step_1")
        assert "step_2" in skipped
        assert "step_3" in skipped

    def test_cascade_skip_no_dependents(self, step_states, steps):
        """TC-03-04-12: 无依赖步骤不级联"""
        selector = StepSelector(step_states)
        skipped = selector._cascade_skip(steps, "step_4")
        assert "step_4" not in skipped


class TestPriority:
    """TC-03-04-13 ~ TC-03-04-15"""

    def test_critical_steps_priority(self, step_states):
        """TC-03-04-13: 关键步骤优先"""
        steps = [
            Step(step_id="step_1", description="A", tool_hint="file", is_critical=False),
            Step(step_id="step_2", description="B", tool_hint="file", is_critical=True),
        ]
        selector = StepSelector(step_states)
        next_step = selector.get_next(steps)
        assert next_step.step_id == "step_2"

    def test_branch_steps_priority(self, step_states):
        """TC-03-04-14: 分支步骤优先"""
        steps = [
            Step(step_id="step_1", description="A", tool_hint="file", is_branch_point=False),
            Step(step_id="step_2", description="B", tool_hint="file", is_branch_point=True),
        ]
        selector = StepSelector(step_states)
        next_step = selector.get_next(steps)
        assert next_step.step_id == "step_2"

    def test_loop_steps_priority(self, step_states):
        """TC-03-04-15: 循环步骤优先"""
        steps = [
            Step(step_id="step_1", description="A", tool_hint="file", is_loop=False),
            Step(step_id="step_2", description="B", tool_hint="file", is_loop=True),
        ]
        selector = StepSelector(step_states)
        next_step = selector.get_next(steps)
        assert next_step.step_id == "step_2"
