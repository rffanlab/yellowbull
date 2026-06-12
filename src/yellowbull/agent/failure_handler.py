"""失败处理模块

重试 + 关键路径阻断 + 级联跳过。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from yellowbull.agent.step_selector import StepSelector
from yellowbull.agent.step_state import StepState
from yellowbull.agent.obstacle_resolver import ObstacleResolver, ObstacleAnalysis
from yellowbull.models.step import Step, StepStatus

logger = logging.getLogger(__name__)


# 默认最大重试次数
DEFAULT_MAX_RETRIES = 3


class FailureHandler:
    """失败处理

    - 重试次数 < max_retries? → 重试
    - 关键步骤失败 → 终止任务
    - 非关键步骤失败 → 跳过 + 级联跳过依赖
    """

    def __init__(
        self,
        step_selector: StepSelector,
        obstacle_resolver: ObstacleResolver | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        self.step_selector = step_selector
        self.obstacle_resolver = obstacle_resolver
        self.max_retries = max_retries

    async def handle_failure(
        self,
        step: Step,
        state: StepState,
        error: str,
        all_steps: list[Step],
    ) -> str:
        """处理步骤失败

        返回: "retry" | "skip" | "abort"
        """
        # 1. 重试判断
        if state.retry_count < self.max_retries:
            state.retry_count += 1
            logger.warning(
                "步骤 %s 失败，尝试重试 (%d/%d): %s",
                step.step_id,
                state.retry_count,
                self.max_retries,
                error,
            )

            # 如果有障碍解决器，尝试分析
            if self.obstacle_resolver:
                analysis = await self.obstacle_resolver.resolve(
                    step, state, error
                )
                if analysis and not analysis.is_recoverable:
                    logger.warning(
                        "障碍分析认为步骤 %s 不可恢复: %s",
                        step.step_id,
                        analysis.cause,
                    )
                    return self._handle_terminal_failure(step, state, all_steps)

            return "retry"

        # 2. 超过最大重试次数
        logger.error(
            "步骤 %s 超过最大重试次数 (%d)，进行终态处理",
            step.step_id,
            self.max_retries,
        )
        return self._handle_terminal_failure(step, state, all_steps)

    def _handle_terminal_failure(
        self,
        step: Step,
        state: StepState,
        all_steps: list[Step],
    ) -> str:
        """终态失败处理

        - 关键步骤 → 终止任务
        - 非关键步骤 → 跳过 + 级联跳过
        """
        state.mark_failed(state.error or "未知错误")

        if step.is_critical:
            logger.error(
                "关键步骤 %s 失败，终止任务",
                step.step_id,
            )
            return "abort"

        # 非关键步骤：跳过 + 级联跳过依赖
        logger.warning(
            "非关键步骤 %s 失败，跳过并级联跳过依赖步骤",
            step.step_id,
        )
        skipped = self.step_selector._cascade_skip(all_steps, step.step_id)
        if skipped:
            logger.info("级联跳过步骤: %s", skipped)

        return "skip"
