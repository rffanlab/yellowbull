"""全局保护模块

预算 + 超时 + 取消检测。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class GuardResult(BaseModel):
    """保护检查结果"""

    ok: bool = Field(description="是否通过检查")
    reason: str | None = Field(default=None, description="终止原因")


class BudgetGuard:
    """全局保护: 预算 + 超时 + 取消检测"""

    def __init__(
        self,
        max_total_steps: int = 100,
        total_timeout: int = 1800,
        step_timeout: int = 120,
    ):
        self.max_total_steps = max_total_steps
        self.total_timeout = total_timeout
        self.step_timeout = step_timeout
        self.steps_consumed = 0
        self._start_time: float | None = None
        self._cancelled = False

    def start(self) -> None:
        """启动计时"""
        self._start_time = time.time()

    def check(self) -> GuardResult:
        """全局保护检查

        - step_budget > 0 ?
        - 未超时 ?
        - 用户未取消 ?
        """
        # 检查取消
        if self._cancelled:
            return GuardResult(ok=False, reason="用户已取消任务")

        # 检查预算
        if self.steps_consumed >= self.max_total_steps:
            return GuardResult(
                ok=False,
                reason=f"步骤预算已耗尽 ({self.steps_consumed}/{self.max_total_steps})",
            )

        # 检查超时
        if self._start_time and self.elapsed_seconds >= self.total_timeout:
            return GuardResult(
                ok=False,
                reason=f"任务超时 ({self.elapsed_seconds:.0f}s/{self.total_timeout}s)",
            )

        return GuardResult(ok=True)

    def consume_step(self) -> None:
        """消耗一步预算"""
        self.steps_consumed += 1

    def cancel(self) -> None:
        """取消任务"""
        self._cancelled = True
        logger.info("任务已被取消")

    @property
    def remaining_budget(self) -> int:
        """剩余预算"""
        return max(0, self.max_total_steps - self.steps_consumed)

    @property
    def elapsed_seconds(self) -> float:
        """已用时间"""
        if self._start_time is None:
            return 0
        return time.time() - self._start_time
