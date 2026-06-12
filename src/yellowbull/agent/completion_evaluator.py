"""完成评估模块

评估任务是否已完成。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from yellowbull.agent.step_state import StepState
from yellowbull.models.step import Step, StepStatus

logger = logging.getLogger(__name__)


class CompletionResult(BaseModel):
    """完成评估结果"""

    is_complete: bool = Field(description="是否完成")
    is_success: bool = Field(description="是否成功完成")
    reason: str = Field(default="", description="完成原因")
    total_steps: int = Field(default=0, description="总步骤数")
    done_steps: int = Field(default=0, description="完成步骤数")
    failed_steps: int = Field(default=0, description="失败步骤数")
    skipped_steps: int = Field(default=0, description="跳过步骤数")


class CompletionEvaluator:
    """完成评估

    评估任务是否已完成:
    - 所有步骤都到达终态 (done/failed/skipped) → 完成
    - 无 pending/running 步骤 → 完成
    """

    def evaluate(
        self,
        steps: list[Step],
        step_states: dict[str, StepState],
    ) -> CompletionResult:
        """评估任务完成状态

        Args:
            steps: 所有步骤
            step_states: 步骤状态映射

        Returns:
            CompletionResult
        """
        total = len(steps)
        done = 0
        failed = 0
        skipped = 0
        running = 0
        pending = 0

        for step in steps:
            state = step_states.get(step.step_id)
            if state is None:
                pending += 1
                continue

            if state.status == StepStatus.DONE:
                done += 1
            elif state.status == StepStatus.FAILED:
                failed += 1
            elif state.status == StepStatus.SKIPPED:
                skipped += 1
            elif state.status == StepStatus.RUNNING:
                running += 1
            else:
                pending += 1

        # 所有步骤都到达终态
        all_terminal = (done + failed + skipped) == total
        has_pending_or_running = (pending + running) > 0

        if all_terminal:
            is_success = failed == 0 or (done + skipped) > (total * 0.5)
            return CompletionResult(
                is_complete=True,
                is_success=is_success,
                reason="所有步骤已执行完毕",
                total_steps=total,
                done_steps=done,
                failed_steps=failed,
                skipped_steps=skipped,
            )

        if not has_pending_or_running:
            return CompletionResult(
                is_complete=True,
                is_success=failed == 0,
                reason="无待执行步骤",
                total_steps=total,
                done_steps=done,
                failed_steps=failed,
                skipped_steps=skipped,
            )

        return CompletionResult(
            is_complete=False,
            is_success=False,
            reason=f"仍有 {pending + running} 个步骤未执行",
            total_steps=total,
            done_steps=done,
            failed_steps=failed,
            skipped_steps=skipped,
        )
