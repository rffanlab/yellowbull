"""T03: 子任务边界场景单元测试"""

import pytest

from yellowbull.agent.execution_stack import ExecutionStack, TaskContext
from yellowbull.agent.step_state import ContextStore, StepState, StepStatus
from yellowbull.models.step import Step
from yellowbull.models.subtask import SubTask
from yellowbull.models.task import Task


class TestSubTaskBoundary:
    """T03-18: 子任务边界场景"""

    def test_empty_subtask_steps(self):
        """TC-03-18-01: 空子任务步骤列表"""
        subtask = SubTask(
            id="sub_1",
            parent_task_id="task_1",
            parent_step_id="step_1",
            goal="完成子任务",
            obstacle_description="障碍",
            steps=[],
        )
        assert subtask.steps == []
        assert len(subtask.steps) == 0

    def test_deep_nested_subtasks(self):
        """TC-03-18-02: 深层嵌套子任务"""
        stack = ExecutionStack(max_depth=10)
        parent_task_id = "task_1"
        parent_step_id = "step_1"

        for i in range(5):
            subtask = SubTask(
                id=f"sub_{i}",
                parent_task_id=parent_task_id,
                parent_step_id=parent_step_id,
                goal=f"goal_{i}",
                obstacle_description=f"obstacle_{i}",
                steps=[],
            )
            ctx = TaskContext(parent_task_id, {}, ContextStore(parent_task_id), 0)
            stack.push(subtask, ctx)
            parent_task_id = subtask.id
            parent_step_id = f"step_{i}"

        assert stack.nesting_depth == 5

    def test_subtask_completion_summary(self):
        """TC-03-18-03: 子任务完成汇总"""
        steps = [
            Step(step_id="s1", description="A", tool_hint="file"),
            Step(step_id="s2", description="B", tool_hint="file"),
            Step(step_id="s3", description="C", tool_hint="file"),
        ]
        subtask = SubTask(
            id="sub_1",
            parent_task_id="task_1",
            parent_step_id="step_1",
            goal="完成子任务",
            obstacle_description="障碍",
            steps=steps,
        )
        step_states = {s.step_id: StepState(s.step_id) for s in steps}
        for state in step_states.values():
            state.mark_done("result")

        assert all(s.status == StepStatus.DONE for s in step_states.values())

    def test_subtask_failure_propagation(self):
        """TC-03-18-04: 子任务失败传播"""
        steps = [
            Step(step_id="s1", description="A", tool_hint="file", is_critical=True),
        ]
        subtask = SubTask(
            id="sub_1",
            parent_task_id="task_1",
            parent_step_id="step_1",
            goal="完成子任务",
            obstacle_description="障碍",
            steps=steps,
        )
        step_states = {s.step_id: StepState(s.step_id) for s in steps}
        step_states["s1"].mark_failed("critical error")

        assert step_states["s1"].status == StepStatus.FAILED

    def test_subtask_timeout(self):
        """TC-03-18-05: 子任务超时由 Guard 控制"""
        from yellowbull.agent.guard import BudgetGuard
        guard = BudgetGuard(max_total_steps=100, total_timeout=0)
        guard.start()
        import time
        time.sleep(0.01)
        result = guard.check()
        assert result.ok is False
