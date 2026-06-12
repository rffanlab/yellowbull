"""执行栈

支持子任务压栈/恢复，实现嵌套任务执行。
"""

from __future__ import annotations

import logging
from typing import Any

from yellowbull.agent.step_state import ContextStore, StepState
from yellowbull.models.step import Step
from yellowbull.models.subtask import SubTask
from yellowbull.models.task import Task

logger = logging.getLogger(__name__)


class TaskContext:
    """被暂停的任务上下文快照"""

    def __init__(
        self,
        task_id: str,
        step_states: dict[str, StepState],
        context_store: ContextStore,
        current_step_index: int,
        paused_at: str | None = None,
    ):
        self.task_id = task_id
        self.step_states = step_states
        self.context_store = context_store
        self.current_step_index = current_step_index
        self.paused_at = paused_at


class ExecutionStack:
    """执行栈: 支持子任务压栈/恢复"""

    def __init__(self, max_depth: int | None = None):
        self.current: Task | SubTask | None = None
        self.paused: list[TaskContext] = []
        self.results: dict[str, Any] = {}
        self.nesting_depth = 0
        self._max_depth = max_depth

    def push(self, subtask: SubTask, parent_context: TaskContext) -> None:
        """压栈: 保存当前任务上下文，切换到子任务"""
        if self._max_depth is not None and self.nesting_depth >= self._max_depth:
            raise RuntimeError(
                f"嵌套深度 {self.nesting_depth} 已达上限 {self._max_depth}"
            )

        self.paused.append(parent_context)
        self.nesting_depth += 1
        self.current = subtask
        logger.info(
            "执行栈压栈: task=%s → subtask=%s (depth=%d)",
            parent_context.task_id,
            subtask.id,
            self.nesting_depth,
        )

    def pop(self) -> TaskContext | None:
        """弹栈: 子任务完成，恢复父任务上下文"""
        if not self.paused:
            return None

        parent_context = self.paused.pop()
        self.nesting_depth -= 1
        self.current = None
        logger.info(
            "执行栈弹栈: 恢复 task=%s (depth=%d)",
            parent_context.task_id,
            self.nesting_depth,
        )
        return parent_context

    def store_result(self, task_id: str, result: Any) -> None:
        """存储任务执行结果"""
        self.results[task_id] = result

    def get_result(self, task_id: str) -> Any | None:
        """获取任务执行结果"""
        return self.results.get(task_id)

    @property
    def is_nested(self) -> bool:
        return self.nesting_depth > 0

    @property
    def depth(self) -> int:
        return self.nesting_depth

    @property
    def is_empty(self) -> bool:
        return self.current is None and not self.paused
