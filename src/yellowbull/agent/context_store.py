"""步骤间数据传递 (ContextStore)

Step 执行完后将结果存入 context_store，后续步骤通过引用 key 获取数据。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from yellowbull.models.step import Step

logger = logging.getLogger(__name__)


class StepOutput(BaseModel):
    """步骤输出数据"""

    step_id: str
    data: Any = None
    output_format: str = "text"
    timestamp: datetime = Field(default_factory=datetime.now)


class ContextStore:
    """步骤间中间结果存储。"""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._data: dict[str, StepOutput] = {}

    def store(self, step_id: str, output: StepOutput) -> None:
        """存储步骤输出。"""
        self._data[step_id] = output
        logger.debug("ContextStore[%s] 存储 step=%s", self.task_id, step_id)

    def get(self, step_id: str) -> StepOutput | None:
        """按 step_id 获取输出。"""
        return self._data.get(step_id)

    def gather_inputs(self, step: Step) -> dict[str, StepOutput]:
        """根据 step.input_from 收集上游步骤输出。

        Raises:
            RuntimeError: 依赖步骤的输出缺失时抛出。
        """
        result = {}
        for upstream_id in step.input_from:
            output = self._data.get(upstream_id)
            if output is None:
                raise RuntimeError(
                    f"步骤 {step.step_id} 的依赖 {upstream_id} 未满足，"
                    f"上游输出缺失"
                )
            result[upstream_id] = output
        return result

    def has_all_inputs(self, step: Step) -> bool:
        """检查步骤的所有输入是否已就绪。"""
        for upstream_id in step.input_from:
            if upstream_id not in self._data:
                return False
        return True

    def clear(self) -> None:
        """清空所有数据。"""
        self._data.clear()

    def __contains__(self, step_id: str) -> bool:
        return step_id in self._data

    def __len__(self) -> int:
        return len(self._data)
