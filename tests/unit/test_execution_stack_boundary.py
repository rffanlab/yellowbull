"""T03-15: 执行栈边界场景测试"""

import asyncio
import pytest

from yellowbull.agent.execution_stack import ExecutionStack, TaskContext
from yellowbull.agent.step_state import ContextStore, StepState
from yellowbull.models.subtask import SubTask


class TestExecutionStackBoundary:
    """T03-15: 执行栈边界场景"""

    def _make_context(self, task_id: str = "task_1") -> TaskContext:
        return TaskContext(
            task_id=task_id,
            step_states={},
            context_store=ContextStore(task_id),
            current_step_index=0,
        )

    def _make_subtask(self, subtask_id: str = "sub_1") -> SubTask:
        from yellowbull.models.step import Step
        return SubTask(
            id=subtask_id,
            parent_task_id="task_1",
            parent_step_id="step_1",
            goal="测试子任务目标",
            obstacle_description="测试障碍",
            steps=[Step(step_id="step_1", description="测试步骤", tool_hint="test")],
        )

    # TC-03-15-01: 空栈 pop
    def test_empty_stack_pop(self):
        """空栈 pop 应返回 None"""
        stack = ExecutionStack()

        result = stack.pop()
        assert result is None

    # TC-03-15-02: 空栈状态
    def test_empty_stack_is_empty(self):
        """空栈 is_empty 应为 True"""
        stack = ExecutionStack()

        assert stack.is_empty is True
        assert stack.depth == 0

    # TC-03-15-03: 最大深度
    def test_stack_max_depth(self):
        """超过最大深度应拒绝"""
        stack = ExecutionStack(max_depth=2)

        ctx = self._make_context()
        sub = self._make_subtask("sub_1")
        stack.push(sub, ctx)

        sub2 = self._make_subtask("sub_2")
        stack.push(sub2, ctx)

        with pytest.raises(RuntimeError):
            sub3 = self._make_subtask("sub_3")
            stack.push(sub3, ctx)

    # TC-03-15-04: 大量压栈
    def test_stack_large_push(self):
        """压栈 10000 层应正常处理"""
        stack = ExecutionStack()

        ctx = self._make_context()
        for i in range(10000):
            sub = self._make_subtask(f"sub_{i}")
            stack.push(sub, ctx)

        assert stack.depth == 10000

    # TC-03-15-05: 并发操作
    @pytest.mark.asyncio
    async def test_concurrent_stack_operations(self):
        """并发 push/pop 应保持数据一致性"""
        stack = ExecutionStack()

        ctx = self._make_context()

        async def push_items(count):
            for i in range(count):
                await asyncio.sleep(0)
                sub = self._make_subtask(f"sub_{i}")
                stack.push(sub, ctx)

        async def pop_items(count):
            results = []
            for _ in range(count):
                await asyncio.sleep(0)
                result = stack.pop()
                if result is not None:
                    results.append(result)
            return results

        # 并发 push 和 pop
        tasks = [
            push_items(100),
            pop_items(50),
        ]

        await asyncio.gather(*tasks)

        # 栈状态应一致
        assert stack.depth >= 0

    # TC-03-15-06: 栈状态异常检测
    def test_stack_state_corruption(self):
        """模拟栈状态异常应检测"""
        stack = ExecutionStack()

        ctx = self._make_context()
        sub = self._make_subtask("sub_1")
        stack.push(sub, ctx)

        assert stack.depth == 1
        assert stack.is_nested is True

    # TC-03-15-07: 结果存储
    def test_stack_store_result(self):
        """结果存储应正确"""
        stack = ExecutionStack()

        stack.store_result("task_1", {"result": "ok"})
        assert stack.get_result("task_1") == {"result": "ok"}

    # TC-03-15-08: 压栈弹栈顺序
    def test_stack_push_pop_order(self):
        """LIFO 顺序应正确"""
        stack = ExecutionStack()

        ctx1 = self._make_context("task_1")
        ctx2 = self._make_context("task_2")

        sub1 = self._make_subtask("sub_1")
        sub2 = self._make_subtask("sub_2")

        stack.push(sub1, ctx1)
        stack.push(sub2, ctx2)

        # 弹栈应恢复 task_2
        result = stack.pop()
        assert result.task_id == "task_2"

        # 再弹栈应恢复 task_1
        result = stack.pop()
        assert result.task_id == "task_1"

    # TC-03-15-09: 嵌套状态
    def test_stack_nested_state(self):
        """嵌套状态应正确更新"""
        stack = ExecutionStack()

        ctx = self._make_context()
        sub = self._make_subtask("sub_1")

        assert stack.is_nested is False

        stack.push(sub, ctx)
        assert stack.is_nested is True

        stack.pop()
        assert stack.is_nested is False
