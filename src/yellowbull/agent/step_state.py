"""步骤状态与上下文存储

定义执行引擎使用的步骤状态、任务级状态和上下文存储。
上下文存储支持命名空间隔离和父子任务继承。
"""

from __future__ import annotations

import logging
from typing import Any

from yellowbull.models.step import StepStatus

logger = logging.getLogger(__name__)


class StepState:
    """单步执行状态"""

    def __init__(self, step_id: str):
        self.step_id = step_id
        self.status = StepStatus.PENDING
        self.result: Any = None
        self.error: str | None = None
        self.retry_count = 0
        self.skipped_by_branch: bool = False
        self.skipped_by_dependency: bool = False

    def mark_running(self) -> None:
        if self.is_terminal:
            return
        self.status = StepStatus.RUNNING

    def mark_done(self, result: Any = None) -> None:
        if self.is_terminal:
            return
        self.status = StepStatus.DONE
        self.result = result

    def mark_failed(self, error: str) -> None:
        if self.is_terminal:
            return
        self.status = StepStatus.FAILED
        self.error = error

    def mark_skipped(self, by_branch: bool = False, by_dependency: bool = False) -> None:
        if self.is_terminal:
            return
        self.status = StepStatus.SKIPPED
        self.skipped_by_branch = by_branch
        self.skipped_by_dependency = by_dependency

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            StepStatus.DONE,
            StepStatus.FAILED,
            StepStatus.SKIPPED,
        )


class TaskState:
    """任务级状态"""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ContextStore:
    """执行上下文存储

    命名空间隔离: task:{task_id}:{step_id} / subtask:{subtask_id}:{step_id}
    子任务可读取父任务 context（只读）
    """

    def __init__(self, task_id: str, namespace: str = "task"):
        self.task_id = task_id
        self._namespace = namespace
        self._store: dict[str, Any] = {}
        self._parent_store: ContextStore | None = None

    def _key(self, step_id: str) -> str:
        return f"{self._namespace}:{self.task_id}:{step_id}"

    def set(self, step_id: str, data: Any) -> None:
        """写入步骤输出数据"""
        key = self._key(step_id)
        self._store[key] = data
        logger.debug("ContextStore[%s:%s] set step=%s", self._namespace, self.task_id, step_id)

    def get(self, step_id: str) -> Any | None:
        """优先本地查找，未命中则回退到父任务 context"""
        key = self._key(step_id)
        if key in self._store:
            return self._store[key]
        if self._parent_store:
            return self._parent_store.get(step_id)
        return None

    def set_parent(self, parent: ContextStore) -> None:
        """设置父级上下文存储（子任务继承父任务上下文）"""
        self._parent_store = parent

    def has(self, step_id: str) -> bool:
        """检查步骤输出是否存在"""
        key = self._key(step_id)
        if key in self._store:
            return True
        if self._parent_store:
            return self._parent_store.has(step_id)
        return False

    def to_dict(self) -> dict:
        return dict(self._store)

    def clear(self) -> None:
        """清空本地存储（不影响父级）"""
        self._store.clear()
