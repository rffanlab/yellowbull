"""T03-06: ExecutionStack 单元测试"""

import pytest

from yellowbull.agent.execution_stack import ExecutionStack, TaskContext
from yellowbull.agent.step_state import ContextStore, StepState, StepStatus
from yellowbull.models.step import Step
from yellowbull.models.subtask import SubTask


@pytest.fixture
def execution_stack():
    return ExecutionStack()


@pytest.fixture
def subtask():
    return SubTask(
        id="sub_1",
        parent_task_id="task_1",
        parent_step_id="step_1",
        goal="解决障碍",
        obstacle_description="文件不存在",
        steps=[],
    )


@pytest.fixture
def task_context():
    store = ContextStore(task_id="task_1")
    return TaskContext(
        task_id="task_1",
        step_states={"step_1": StepState("step_1")},
        context_store=store,
        current_step_index=0,
    )


@pytest.fixture
def subtask2():
    return SubTask(
        id="sub_2",
        parent_task_id="sub_1",
        parent_step_id="step_2",
        goal="解决子障碍",
        obstacle_description="权限不足",
        steps=[],
    )


@pytest.fixture
def task_context2():
    store = ContextStore(task_id="sub_1")
    return TaskContext(
        task_id="sub_1",
        step_states={"step_2": StepState("step_2")},
        context_store=store,
        current_step_index=0,
    )


class TestExecutionStackInit:
    """TC-03-06-01 ~ TC-03-06-03: 初始化"""

    def test_initial_state(self):
        """TC-03-06-01: 初始状态"""
        stack = ExecutionStack()
        assert stack.current is None
        assert stack.paused == []
        assert stack.results == {}
        assert stack.nesting_depth == 0

    def test_initial_is_empty(self):
        """TC-03-06-02: 初始为空"""
        stack = ExecutionStack()
        assert stack.is_empty is True

    def test_initial_not_nested(self):
        """TC-03-06-03: 初始未嵌套"""
        stack = ExecutionStack()
        assert stack.is_nested is False


class TestExecutionStackPush:
    """TC-03-06-04 ~ TC-03-06-09: 压栈"""

    def test_push_subtask(self, execution_stack, subtask, task_context):
        """TC-03-06-04: 压栈子任务"""
        execution_stack.push(subtask, task_context)
        assert execution_stack.current == subtask
        assert len(execution_stack.paused) == 1
        assert execution_stack.paused[0].task_id == "task_1"
        assert execution_stack.nesting_depth == 1

    def test_push_sets_nested(self, execution_stack, subtask, task_context):
        """TC-03-06-05: 压栈后设置嵌套"""
        execution_stack.push(subtask, task_context)
        assert execution_stack.is_nested is True
        assert execution_stack.is_empty is False

    def test_push_depth(self, execution_stack, subtask, task_context):
        """TC-03-06-06: 压栈后深度"""
        execution_stack.push(subtask, task_context)
        assert execution_stack.depth == 1

    def test_push_multiple(self, execution_stack, subtask, task_context, subtask2, task_context2):
        """TC-03-06-07: 多次压栈"""
        execution_stack.push(subtask, task_context)
        execution_stack.push(subtask2, task_context2)
        assert execution_stack.current == subtask2
        assert len(execution_stack.paused) == 2
        assert execution_stack.nesting_depth == 2

    def test_push_max_depth(self):
        """TC-03-06-08: 超过最大深度"""
        stack = ExecutionStack(max_depth=1)
        sub1 = SubTask(
            id="sub_1", parent_task_id="task_1", parent_step_id="step_1",
            goal="g1", obstacle_description="o1", steps=[],
        )
        ctx1 = TaskContext("task_1", {}, ContextStore("task_1"), 0)
        stack.push(sub1, ctx1)
        assert stack.nesting_depth == 1

        sub2 = SubTask(
            id="sub_2", parent_task_id="sub_1", parent_step_id="step_2",
            goal="g2", obstacle_description="o2", steps=[],
        )
        ctx2 = TaskContext("sub_1", {}, ContextStore("sub_1"), 0)
        with pytest.raises(RuntimeError, match="嵌套深度"):
            stack.push(sub2, ctx2)

    def test_push_no_max_depth(self, execution_stack, subtask, task_context):
        """TC-03-06-09: 无最大深度限制"""
        execution_stack.push(subtask, task_context)
        assert execution_stack.nesting_depth == 1


class TestExecutionStackPop:
    """TC-03-06-10 ~ TC-03-06-15: 弹栈"""

    def test_pop(self, execution_stack, subtask, task_context):
        """TC-03-06-10: 弹栈"""
        execution_stack.push(subtask, task_context)
        ctx = execution_stack.pop()
        assert ctx is not None
        assert ctx.task_id == "task_1"
        assert execution_stack.nesting_depth == 0

    def test_pop_empty(self, execution_stack):
        """TC-03-06-11: 空栈弹栈"""
        result = execution_stack.pop()
        assert result is None

    def test_pop_restores_empty(self, execution_stack, subtask, task_context):
        """TC-03-06-12: 弹栈后恢复空"""
        execution_stack.push(subtask, task_context)
        execution_stack.pop()
        assert execution_stack.is_empty is True

    def test_pop_restores_not_nested(self, execution_stack, subtask, task_context):
        """TC-03-06-13: 弹栈后恢复未嵌套"""
        execution_stack.push(subtask, task_context)
        execution_stack.pop()
        assert execution_stack.is_nested is False

    def test_pop_multiple(self, execution_stack, subtask, task_context, subtask2, task_context2):
        """TC-03-06-14: 多次弹栈"""
        execution_stack.push(subtask, task_context)
        execution_stack.push(subtask2, task_context2)

        ctx = execution_stack.pop()
        assert ctx.task_id == "sub_1"
        assert execution_stack.nesting_depth == 1

        ctx = execution_stack.pop()
        assert ctx.task_id == "task_1"
        assert execution_stack.nesting_depth == 0

    def test_pop_lifo(self, execution_stack, subtask, task_context, subtask2, task_context2):
        """TC-03-06-15: LIFO 顺序"""
        execution_stack.push(subtask, task_context)
        execution_stack.push(subtask2, task_context2)

        ctx = execution_stack.pop()
        # 后压栈的先弹出
        assert ctx.task_id == "sub_1"


class TestExecutionStackResults:
    """TC-03-06-16 ~ TC-03-06-19: 结果存储"""

    def test_store_result(self, execution_stack):
        """TC-03-06-16: 存储结果"""
        execution_stack.store_result("task_1", {"key": "value"})
        assert execution_stack.get_result("task_1") == {"key": "value"}

    def test_get_missing_result(self, execution_stack):
        """TC-03-06-17: 获取不存在结果"""
        assert execution_stack.get_result("nonexistent") is None

    def test_store_multiple_results(self, execution_stack):
        """TC-03-06-18: 存储多个结果"""
        execution_stack.store_result("task_1", "result1")
        execution_stack.store_result("task_2", "result2")
        assert execution_stack.get_result("task_1") == "result1"
        assert execution_stack.get_result("task_2") == "result2"

    def test_overwrite_result(self, execution_stack):
        """TC-03-06-19: 覆盖结果"""
        execution_stack.store_result("task_1", "old")
        execution_stack.store_result("task_1", "new")
        assert execution_stack.get_result("task_1") == "new"


class TestExecutionStackLifecycle:
    """TC-03-06-20 ~ TC-03-06-23: 完整生命周期"""

    def test_full_lifecycle(self, execution_stack, subtask, task_context):
        """TC-03-06-20: 压栈 -> 执行 -> 弹栈"""
        # 初始空
        assert execution_stack.is_empty is True

        # 压栈
        execution_stack.push(subtask, task_context)
        assert execution_stack.is_nested is True

        # 存储结果
        execution_stack.store_result("sub_1", "done")

        # 弹栈
        ctx = execution_stack.pop()
        assert ctx is not None
        assert execution_stack.is_empty is True

    def test_nested_lifecycle(self, execution_stack, subtask, task_context, subtask2, task_context2):
        """TC-03-06-21: 嵌套压栈弹栈"""
        execution_stack.push(subtask, task_context)
        execution_stack.push(subtask2, task_context2)
        assert execution_stack.nesting_depth == 2

        execution_stack.pop()
        assert execution_stack.nesting_depth == 1

        execution_stack.pop()
        assert execution_stack.nesting_depth == 0

    def test_max_depth_lifecycle(self):
        """TC-03-06-22: 最大深度限制生命周期"""
        stack = ExecutionStack(max_depth=2)

        sub1 = SubTask(id="s1", parent_task_id="t1", parent_step_id="st1", goal="g", obstacle_description="o", steps=[])
        ctx1 = TaskContext("t1", {}, ContextStore("t1"), 0)
        stack.push(sub1, ctx1)

        sub2 = SubTask(id="s2", parent_task_id="s1", parent_step_id="st2", goal="g", obstacle_description="o", steps=[])
        ctx2 = TaskContext("s1", {}, ContextStore("s1"), 0)
        stack.push(sub2, ctx2)

        assert stack.nesting_depth == 2

        sub3 = SubTask(id="s3", parent_task_id="s2", parent_step_id="st3", goal="g", obstacle_description="o", steps=[])
        ctx3 = TaskContext("s2", {}, ContextStore("s2"), 0)
        with pytest.raises(RuntimeError):
            stack.push(sub3, ctx3)

    def test_depth_property(self, execution_stack, subtask, task_context):
        """TC-03-06-23: depth 属性"""
        assert execution_stack.depth == 0
        execution_stack.push(subtask, task_context)
        assert execution_stack.depth == 1
        execution_stack.pop()
        assert execution_stack.depth == 0


class TestExecutionStackBoundary:
    """T03-15: ExecutionStack 边界场景"""

    def test_push_pop_balance(self, execution_stack, subtask, task_context):
        """TC-03-15-01: 压栈弹栈平衡"""
        execution_stack.push(subtask, task_context)
        execution_stack.pop()
        assert execution_stack.is_empty is True
        assert execution_stack.nesting_depth == 0

    def test_deep_nesting(self):
        """TC-03-15-02: 深度嵌套"""
        stack = ExecutionStack(max_depth=10)
        prev_task_id = "task_1"
        for i in range(5):
            sub = SubTask(
                id=f"sub_{i}", parent_task_id=prev_task_id, parent_step_id=f"step_{i}",
                goal=f"g{i}", obstacle_description=f"o{i}", steps=[],
            )
            ctx = TaskContext(prev_task_id, {}, ContextStore(prev_task_id), 0)
            stack.push(sub, ctx)
            prev_task_id = sub.id
        assert stack.nesting_depth == 5

    def test_max_depth_zero(self):
        """TC-03-15-03: 最大深度为0"""
        stack = ExecutionStack(max_depth=0)
        sub = SubTask(
            id="sub_1", parent_task_id="task_1", parent_step_id="step_1",
            goal="g1", obstacle_description="o1", steps=[],
        )
        ctx = TaskContext("task_1", {}, ContextStore("task_1"), 0)
        with pytest.raises(RuntimeError, match="嵌套深度"):
            stack.push(sub, ctx)

    def test_result_persistence(self, execution_stack):
        """TC-03-15-04: 结果持久化"""
        execution_stack.store_result("task_1", "result1")
        execution_stack.store_result("task_2", "result2")
        assert execution_stack.get_result("task_1") == "result1"
        assert execution_stack.get_result("task_2") == "result2"
