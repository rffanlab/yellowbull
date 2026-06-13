"""重试决策模块

根据失败分析生成重试选项，支持多种重试模式。
"""

from __future__ import annotations

import logging

from yellowbull.models.result import (
    EvaluationResult,
    RetryMode,
    RetryOption,
)
from yellowbull.models.step import StepStatus

logger = logging.getLogger(__name__)


class RetryManager:
    """T04-06 重试管理器"""

    def __init__(self):
        pass

    def generate_retry_options(
        self, evaluation: EvaluationResult, total_steps: int, done_steps: int
    ) -> list[RetryOption]:
        """根据评估结果生成重试选项"""
        options = []

        if evaluation.conclusion == "success":
            return options  # 成功不需要重试

        completion_rate = done_steps / total_steps if total_steps > 0 else 0

        # 全量重试：始终可用
        options.append(
            RetryOption(
                mode=RetryMode.FULL,
                description="从头重新执行整个任务",
            )
        )

        # 部分重试：仅当有已完成步骤时
        if done_steps > 0:
            remaining = total_steps - done_steps
            options.append(
                RetryOption(
                    mode=RetryMode.PARTIAL,
                    description=f"从失败处继续，剩余 {remaining} 个步骤",
                )
            )

        # 修复后重试：当有明确失败原因时
        if evaluation.failure_analysis:
            options.append(
                RetryOption(
                    mode=RetryMode.FIX,
                    description="根据分析结果修复问题后重试",
                )
            )

        # 放弃：始终可用（非成功结论）
        options.append(
            RetryOption(
                mode=RetryMode.ABANDON,
                description="放弃任务，保留已完成的结果",
            )
        )

        return options

    @staticmethod
    def recommend_mode(evaluation: EvaluationResult, done_steps: int) -> str | None:
        """推荐重试模式"""
        if evaluation.conclusion == "success":
            return None

        # 失败但有明确原因 → 修复后重试
        if evaluation.failure_analysis and done_steps > 0:
            return RetryMode.FIX

        # 完成度高但少量失败 → 部分重试
        if evaluation.achievement_score > 0.5:
            return RetryMode.PARTIAL

        # 低完成度 → 全量重试
        return RetryMode.FULL


__all__ = ["RetryManager"]
